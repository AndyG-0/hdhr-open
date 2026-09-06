"""OpenAI-compatible chat completions client.

Covers OpenAI itself as well as any provider speaking the same
`/chat/completions` wire format with an OpenAI-shaped `tools`/streaming
contract — Ollama, vLLM, LM Studio, OpenRouter, DeepSeek, etc. Only
`base_url` (and which models exist) differs between them; `get_ai_client`
routes "openai", "ollama", and "custom" all here.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.integrations.ai import (
    BaseAIClient,
    ChatMessage,
    StreamEvent,
    ToolCallRequest,
    ToolSpec,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT = 60.0
TEST_CONNECTION_TIMEOUT = 15.0

# /v1/models lists every model the account can use, chat and non-chat alike —
# filter out the obviously-non-chat families rather than allow-listing chat
# model name patterns, since a name-based allow-list goes stale the same way
# a hardcoded model list would.
_NON_CHAT_MODEL_MARKERS = ("embedding", "whisper", "tts", "dall-e", "moderation", "davinci", "babbage")


def _clamp_temperature(temperature: float) -> float:
    return max(0.0, min(2.0, temperature))


def _to_wire_messages(messages: list[ChatMessage], *, system_prompt: str) -> list[dict[str, Any]]:
    wire: list[dict[str, Any]] = []
    if system_prompt:
        wire.append({"role": "system", "content": system_prompt})
    for msg in messages:
        if msg.role == "tool":
            assert msg.tool_result is not None
            wire.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_result.tool_call_id,
                    "content": json.dumps(msg.tool_result.content),
                }
            )
        elif msg.tool_calls:
            wire.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
        else:
            wire.append({"role": msg.role, "content": msg.content or ""})
    return wire


def _to_wire_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": t.parameters},
        }
        for t in tools
    ]


class OpenAIClient(BaseAIClient):
    def __init__(self, *, api_key: str, base_url: str | None, model: str) -> None:
        super().__init__(api_key=api_key, base_url=(base_url or DEFAULT_BASE_URL).rstrip("/"), model=model)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def test_connection(self) -> tuple[bool, str]:
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": "ping"}],
            # No token cap: reasoning models (o-series, gpt-5) spend the
            # completion-token budget on hidden reasoning tokens before any
            # visible output, so even a small cap reliably fails on them —
            # this is a one-off connectivity check, not a cost-sensitive call.
            "stream": False,
        }
        try:
            async with httpx.AsyncClient(timeout=TEST_CONNECTION_TIMEOUT) as client:
                resp = await client.post(f"{self.base_url}/chat/completions", json=body, headers=self._headers())
        except httpx.HTTPError as exc:
            return False, f"Connection failed: {exc}"

        if resp.status_code == 200:
            return True, f"Connected (model: {self.model})"
        detail = _extract_error_detail(resp)
        return False, f"HTTP {resp.status_code}: {detail}"

    async def list_models(self) -> tuple[bool, list[str], str]:
        try:
            async with httpx.AsyncClient(timeout=TEST_CONNECTION_TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/models", headers=self._headers())
        except httpx.HTTPError as exc:
            return False, [], f"Connection failed: {exc}"

        if resp.status_code != 200:
            return False, [], f"HTTP {resp.status_code}: {_extract_error_detail(resp)}"

        entries = resp.json().get("data") or []
        ids = [e["id"] for e in entries if isinstance(e, dict) and e.get("id")]
        chat_ids = [i for i in ids if not any(marker in i for marker in _NON_CHAT_MODEL_MARKERS)]
        return True, sorted(chat_ids), ""

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec],
        system_prompt: str,
        temperature: float,
    ) -> AsyncIterator[StreamEvent]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": _to_wire_messages(messages, system_prompt=system_prompt),
            "temperature": _clamp_temperature(temperature),
            "stream": True,
        }
        if tools:
            body["tools"] = _to_wire_tools(tools)

        # Accumulated per tool_call index, since OpenAI streams each tool
        # call's id/name/arguments incrementally across many deltas.
        pending_calls: dict[int, dict[str, str]] = {}

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                # At most 3 attempts: some reasoning models (o-series, gpt-5)
                # reject function tools combined with their default
                # reasoning_effort, and/or reject any non-default
                # `temperature` outright — rather than guessing which models
                # need this upfront (a model-name allow-list goes stale the
                # same way a hardcoded model list would), retry with each
                # dropped if the provider says so.
                max_attempts = 3
                for attempt in range(max_attempts):
                    async with client.stream(
                        "POST", f"{self.base_url}/chat/completions", json=body, headers=self._headers()
                    ) as resp:
                        if resp.status_code != 200:
                            await resp.aread()
                            detail = _extract_error_detail(resp)
                            retriable = attempt < max_attempts - 1
                            if retriable and tools and "reasoning_effort" in detail:
                                body["reasoning_effort"] = "none"
                                continue
                            if retriable and "temperature" in body and "'temperature'" in detail and "does not support" in detail:
                                del body["temperature"]
                                continue
                            yield StreamEvent(type="error", text=f"HTTP {resp.status_code}: {detail}")
                            return
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue
                            data = line[len("data:") :].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                            except json.JSONDecodeError:
                                continue
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            delta = choices[0].get("delta") or {}
                            content = delta.get("content")
                            if content:
                                yield StreamEvent(type="token", text=content)
                            for tc_delta in delta.get("tool_calls") or []:
                                index = tc_delta.get("index", 0)
                                entry = pending_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                                if tc_delta.get("id"):
                                    entry["id"] = tc_delta["id"]
                                function = tc_delta.get("function") or {}
                                if function.get("name"):
                                    entry["name"] += function["name"]
                                if function.get("arguments"):
                                    entry["arguments"] += function["arguments"]
                    break
        except httpx.HTTPError as exc:
            yield StreamEvent(type="error", text=f"Connection failed: {exc}")
            return

        for entry in pending_calls.values():
            try:
                arguments = json.loads(entry["arguments"]) if entry["arguments"] else {}
            except json.JSONDecodeError:
                logger.warning("OpenAI tool call arguments were not valid JSON: %r", entry["arguments"])
                arguments = {}
            yield StreamEvent(
                type="tool_call", tool_call=ToolCallRequest(id=entry["id"], name=entry["name"], arguments=arguments)
            )
        yield StreamEvent(type="message_end")


def _extract_error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        return str(data.get("error", {}).get("message", resp.text))
    except Exception:
        return resp.text[:200]
