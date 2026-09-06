"""Google Gemini `generateContent` client.

Differs from OpenAI/Anthropic in a few load-bearing ways: the API key is a
query parameter, not a header; roles are "user"/"model" (a tool result goes
back as role "function"); the system prompt is a separate top-level
`systemInstruction` field; and Gemini has no call-id concept at all, so this
client synthesizes one (`uuid4()`) per function call it sees streamed back —
that id only needs to round-trip within this backend's own transcript
tracking, since outgoing function responses are matched by name, not id.
"""

from __future__ import annotations

import json
import logging
import uuid
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

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_TIMEOUT = 60.0
TEST_CONNECTION_TIMEOUT = 15.0


def _clamp_temperature(temperature: float) -> float:
    return max(0.0, min(2.0, temperature))


def _to_wire_contents(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    wire: list[dict[str, Any]] = []
    for msg in messages:
        if msg.role == "system":
            continue
        if msg.role == "tool":
            assert msg.tool_result is not None
            wire.append(
                {
                    "role": "function",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": msg.tool_result.name,
                                "response": msg.tool_result.content,
                            }
                        }
                    ],
                }
            )
        elif msg.tool_calls:
            parts: list[dict[str, Any]] = []
            if msg.content:
                parts.append({"text": msg.content})
            for tc in msg.tool_calls:
                parts.append({"functionCall": {"name": tc.name, "args": tc.arguments}})
            wire.append({"role": "model", "parts": parts})
        else:
            role = "model" if msg.role == "assistant" else "user"
            wire.append({"role": role, "parts": [{"text": msg.content or ""}]})
    return wire


def _to_wire_tools(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "functionDeclarations": [
                {"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools
            ]
        }
    ]


class GeminiClient(BaseAIClient):
    def __init__(self, *, api_key: str, base_url: str | None, model: str) -> None:
        super().__init__(api_key=api_key, base_url=(base_url or DEFAULT_BASE_URL).rstrip("/"), model=model)

    async def test_connection(self) -> tuple[bool, str]:
        body = {
            "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
            "generationConfig": {"maxOutputTokens": 1},
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"
        try:
            async with httpx.AsyncClient(timeout=TEST_CONNECTION_TIMEOUT) as client:
                resp = await client.post(url, params={"key": self.api_key}, json=body)
        except httpx.HTTPError as exc:
            return False, f"Connection failed: {exc}"

        if resp.status_code == 200:
            return True, f"Connected (model: {self.model})"
        detail = _extract_error_detail(resp)
        return False, f"HTTP {resp.status_code}: {detail}"

    async def list_models(self) -> tuple[bool, list[str], str]:
        try:
            async with httpx.AsyncClient(timeout=TEST_CONNECTION_TIMEOUT) as client:
                resp = await client.get(f"{self.base_url}/models", params={"key": self.api_key})
        except httpx.HTTPError as exc:
            return False, [], f"Connection failed: {exc}"

        if resp.status_code != 200:
            return False, [], f"HTTP {resp.status_code}: {_extract_error_detail(resp)}"

        # Filtered by the capability Gemini itself reports (supports
        # generateContent) rather than by name, so it naturally excludes
        # embedding/imagen/veo models without a name-pattern guess.
        entries = resp.json().get("models") or []
        ids = []
        for entry in entries:
            name = entry.get("name") or ""
            if name and "generateContent" in (entry.get("supportedGenerationMethods") or []):
                ids.append(name.removeprefix("models/"))
        return True, sorted(ids), ""

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec],
        system_prompt: str,
        temperature: float,
    ) -> AsyncIterator[StreamEvent]:
        body: dict[str, Any] = {
            "contents": _to_wire_contents(messages),
            "generationConfig": {"temperature": _clamp_temperature(temperature)},
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        if tools:
            body["tools"] = _to_wire_tools(tools)

        url = f"{self.base_url}/models/{self.model}:streamGenerateContent"
        pending_calls: list[tuple[str, dict[str, Any]]] = []

        try:
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                async with client.stream("POST", url, params={"alt": "sse", "key": self.api_key}, json=body) as resp:
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
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        candidates = chunk.get("candidates") or []
                        if not candidates:
                            continue
                        content = candidates[0].get("content") or {}
                        for part in content.get("parts") or []:
                            if "text" in part and part["text"]:
                                yield StreamEvent(type="token", text=part["text"])
                            elif "functionCall" in part:
                                call = part["functionCall"]
                                pending_calls.append((call.get("name", ""), call.get("args") or {}))
        except httpx.HTTPError as exc:
            yield StreamEvent(type="error", text=f"Connection failed: {exc}")
            return

        for name, args in pending_calls:
            yield StreamEvent(
                type="tool_call", tool_call=ToolCallRequest(id=uuid.uuid4().hex, name=name, arguments=args)
            )
        yield StreamEvent(type="message_end")


def _extract_error_detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        error = data.get("error", {}) if isinstance(data, dict) else {}
        return str(error.get("message", resp.text))
    except Exception:
        return resp.text[:200]
