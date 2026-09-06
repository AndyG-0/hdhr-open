"""Anthropic (Claude) Messages API client.

Unlike OpenAI, the system prompt is a top-level `system` field rather than a
message, tool results come back to the model as a `role: "user"` message
containing a `tool_result` content block (not a dedicated "tool" role), and
streaming is a sequence of typed SSE events (`content_block_start` /
`content_block_delta` / ...) rather than one `delta` object per chunk.
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

DEFAULT_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_TIMEOUT = 60.0
TEST_CONNECTION_TIMEOUT = 15.0
DEFAULT_MAX_TOKENS = 4096


def _clamp_temperature(temperature: float) -> float:
    return max(0.0, min(1.0, temperature))


def _to_wire_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    wire: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "system":
            # System prompt is handled separately as a top-level field.
            continue
        if msg.role == "tool":
            assert msg.tool_result is not None
            wire.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": msg.tool_result.tool_call_id,
                            "content": json.dumps(msg.tool_result.content),
                        }
                    ],
                }
            )
        elif msg.tool_calls:
            content: list[dict[str, Any]] = []
            if msg.content:
                content.append({"type": "text", "text": msg.content})
            for tc in msg.tool_calls:
                content.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
            wire.append({"role": "assistant", "content": content})
        else:
            wire.append({"role": msg.role, "content": msg.content or ""})
    return wire


def _to_wire_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]


class AnthropicClient(BaseAIClient):
    def __init__(self, *, api_key: str, base_url: str | None, model: str) -> None:
        super().__init__(api_key=api_key, base_url=(base_url or DEFAULT_BASE_URL).rstrip("/"), model=model)

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }

    async def test_connection(self) -> tuple[bool, str]:
        body = {
            "model": self.model,
            "max_tokens": 1,
            "messages": [{"role": "user", "content": "ping"}],
        }
        try:
            async with httpx.AsyncClient(timeout=TEST_CONNECTION_TIMEOUT) as client:
                resp = await client.post(f"{self.base_url}/messages", json=body, headers=self._headers())
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

        # Left in the API's own order (newest-first) rather than sorted
        # alphabetically, which would bury current models under old ones.
        entries = resp.json().get("data") or []
        ids = [e["id"] for e in entries if isinstance(e, dict) and e.get("id")]
        return True, ids, ""

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
            "max_tokens": DEFAULT_MAX_TOKENS,
            "system": system_prompt,
            "messages": _to_wire_messages(messages),
            "temperature": _clamp_temperature(temperature),
            "stream": True,
        }
        if tools:
            body["tools"] = _to_wire_tools(tools)

        # Keyed by content-block index, populated from content_block_start
        # so a later content_block_delta knows whether it's text or a
        # tool_use's incrementally-streamed JSON input.
        blocks: dict[int, dict[str, str]] = {}

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                async with client.stream(
                    "POST", f"{self.base_url}/messages", json=body, headers=self._headers()
                ) as resp:
                    if resp.status_code != 200:
                        await resp.aread()
                        detail = _extract_error_detail(resp)
                        yield StreamEvent(type="error", text=f"HTTP {resp.status_code}: {detail}")
                        return
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if not data:
                            continue
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        event_type = event.get("type")

                        if event_type == "content_block_start":
                            index = event.get("index", 0)
                            block = event.get("content_block") or {}
                            if block.get("type") == "tool_use":
                                blocks[index] = {
                                    "kind": "tool_use",
                                    "id": block.get("id", ""),
                                    "name": block.get("name", ""),
                                    "json": "",
                                }
                            else:
                                blocks[index] = {"kind": "text"}
                        elif event_type == "content_block_delta":
                            index = event.get("index", 0)
                            delta = event.get("delta") or {}
                            entry = blocks.get(index)
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield StreamEvent(type="token", text=text)
                            elif delta.get("type") == "input_json_delta" and entry is not None:
                                entry["json"] = entry.get("json", "") + delta.get("partial_json", "")
                        elif event_type == "error":
                            error = event.get("error") or {}
                            yield StreamEvent(type="error", text=error.get("message", "Unknown error"))
                            return
                        elif event_type == "message_stop":
                            break
        except httpx.HTTPError as exc:
            yield StreamEvent(type="error", text=f"Connection failed: {exc}")
            return

        for entry in blocks.values():
            if entry.get("kind") != "tool_use":
                continue
            try:
                arguments = json.loads(entry["json"]) if entry["json"] else {}
            except json.JSONDecodeError:
                logger.warning("Anthropic tool_use input was not valid JSON: %r", entry["json"])
                arguments = {}
            yield StreamEvent(
                type="tool_call",
                tool_call=ToolCallRequest(id=entry["id"], name=entry["name"], arguments=arguments),
            )
        yield StreamEvent(type="message_end")


def _extract_error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        return str(data.get("error", {}).get("message", resp.text))
    except Exception:
        return resp.text[:200]
