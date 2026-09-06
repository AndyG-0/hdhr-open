"""AI assistant: connection testing (AI-1), the streaming chat endpoint, and
the action confirm/cancel endpoints (AI-3).

Reuses the generic `ai` network-integration row (see
`app.api.network_settings.KNOWN_INTEGRATION_TYPES`) for provider/api_key/
base_url/model/system_prompt_custom/temperature/enable_recording_tools —
this router only adds the behavior the generic CRUD routes can't express.

`/chat` is stateless — there's no server-side conversation-history table —
but unlike a plain text-only transcript, the client resends *structured*
tool-call/tool-result history too (see `WireMessage`/`_parse_messages`),
mirroring the richer transcript the orchestration loop below builds
internally (including tool_calls/tool_results, `ai.py` lines below). That's
what lets the model resolve a later turn like "all of those games" against
an earlier tool result instead of needing to re-call the tool. To bound
per-turn payload/token growth over a long conversation, only the most
recent `_MAX_RESENT_TOOL_EXCHANGES` tool exchanges are kept — older ones are
collapsed down to their plain assistant text (see `_cap_resent_tool_history`).

Mutating tools are never executed from `/chat` — `registry.dispatch()` only
ever calls a mutating tool's `preview` (see `app.ai.tools.registry`). The
*only* place in this file that touches `execute` is `confirm_ai_action`,
after a human has explicitly clicked Confirm on a specific action_id.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.ai.tools import registry
from app.auth import get_current_admin, get_current_user
from app.integrations.ai import ChatMessage, ToolCallRequest, ToolCallResultMessage, get_ai_client
from app.storage.db import get_network_integration

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(get_current_user)])

_MAX_TOOL_ITERATIONS = 6
_MAX_RESENT_TOOL_EXCHANGES = 3

_BASELINE_SYSTEM_PROMPT = (
    "You are the AI assistant built into an HDHomeRun-based live TV/DVR server. "
    "You can search the program guide and, only if the operator has enabled it, "
    "look at and propose changes to DVR recording rules and recordings using the "
    "tools available to you. If the user asks you to schedule, cancel, or delete "
    "a recording and you have no recording tools available, tell them plainly "
    "that recording isn't enabled for the assistant yet, and that an admin can "
    "turn it on in Settings under the AI Assistant integration — don't just say "
    "you're unable to help.\n\n"
    "Scheduling, cancelling, or deleting anything is never done directly by a "
    "tool call — calling one of those tools only proposes the action, which is "
    "shown to the user as a confirmation card they must explicitly click Confirm "
    "on. You have no way to force it through. Never tell the user something has "
    "been scheduled, cancelled, or deleted just because you called the tool for "
    "it — only say that once a tool result actually confirms it happened.\n\n"
    "When a search or lookup tool returns more than one result, present them "
    "to the user as a numbered list (1., 2., 3., ...) so they can refer back "
    "to a specific one. If the user's next message answers with a number "
    "('2'), an ordinal ('the first one'), or a collective reference ('all of "
    "those', 'all of them'), resolve it against the structured results "
    "already in this conversation's history rather than searching again — "
    "the exact channel, date_time, and other fields you need are already "
    "available from the earlier tool result. Only call a search tool again "
    "if the user is clearly asking about something new. If you genuinely "
    "don't have enough information to proceed (e.g. the earlier results are "
    "no longer in view, or the reference is ambiguous), ask a clarifying "
    "question instead of saying you were unable to help."
)


async def _get_ai_settings(candidate_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = await asyncio.to_thread(get_network_integration, "ai")
    return {**(existing["settings"] if existing else {}), **(candidate_payload or {})}


def _build_system_prompt(*, custom: str, context: dict[str, Any]) -> str:
    parts = [_BASELINE_SYSTEM_PROMPT]
    context_lines = [f"- {key}: {value}" for key, value in context.items() if value not in (None, "")]
    if context_lines:
        parts.append("Current context:\n" + "\n".join(context_lines))
    if custom:
        parts.append(custom)
    return "\n\n".join(parts)


class WireToolCall(BaseModel):
    """One tool call as resent by the client — mirrors `ToolCallRequest`."""

    id: str
    name: str
    arguments: dict[str, Any] | None = Field(default_factory=dict)


class WireMessage(BaseModel):
    """One transcript entry as resent by the client. `content` is a plain
    string for "user"/"assistant" text turns, or the tool's JSON result dict
    for a "tool" turn (see `content_text`/`content_dict`). All fields beyond
    `role` are optional so a legacy plain-text-only client keeps working
    unchanged."""

    role: Literal["user", "assistant", "tool"]
    content: str | dict[str, Any] | None = None
    tool_calls: list[WireToolCall] | None = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    def content_text(self) -> str | None:
        return self.content if isinstance(self.content, str) else None

    def content_dict(self) -> dict[str, Any]:
        return self.content if isinstance(self.content, dict) else {}


class ChatRequest(BaseModel):
    messages: list[WireMessage] = Field(default_factory=list)
    context: dict[str, Any] | None = Field(default_factory=dict)


def _drop_orphaned_tool_results(messages: list[ChatMessage]) -> list[ChatMessage]:
    """Drops any "tool" message whose `tool_call_id` doesn't belong to the
    immediately preceding assistant `tool_calls` — a malformed/stale client
    payload would otherwise reach the provider as a dangling tool result,
    which most providers reject outright."""
    result: list[ChatMessage] = []
    pending_ids: set[str] = set()
    for msg in messages:
        if msg.role == "assistant" and msg.tool_calls:
            pending_ids = {call.id for call in msg.tool_calls}
            result.append(msg)
        elif msg.role == "tool":
            if msg.tool_result and msg.tool_result.tool_call_id in pending_ids:
                result.append(msg)
        else:
            pending_ids = set()
            result.append(msg)
    return result


def _cap_resent_tool_history(
    messages: list[ChatMessage], *, max_exchanges: int = _MAX_RESENT_TOOL_EXCHANGES
) -> list[ChatMessage]:
    """Keeps only the most recent `max_exchanges` tool-calling exchanges
    (an assistant `tool_calls` entry plus its `tool` result entries) intact.
    Older exchanges are collapsed down to just the assistant's plain text
    (if any) — the conversation still has that turn's summary, just not the
    full structured payload — bounding how much a long conversation's resent
    history grows per turn."""
    tool_block_starts = [i for i, m in enumerate(messages) if m.role == "assistant" and m.tool_calls]
    if len(tool_block_starts) <= max_exchanges:
        return messages
    stale_starts = set(tool_block_starts[:-max_exchanges])

    result: list[ChatMessage] = []
    stripping = False
    for i, msg in enumerate(messages):
        if i in stale_starts:
            if msg.content:
                result.append(ChatMessage(role="assistant", content=msg.content))
            stripping = True
            continue
        if stripping and msg.role == "tool":
            continue
        stripping = False
        result.append(msg)
    return result


def _parse_messages(raw: list[WireMessage]) -> list[ChatMessage]:
    messages: list[ChatMessage] = []
    for entry in raw:
        if entry.role == "tool":
            if not entry.tool_call_id or not entry.name:
                continue  # malformed — drop rather than fail the whole turn
            messages.append(
                ChatMessage(
                    role="tool",
                    tool_result=ToolCallResultMessage(
                        tool_call_id=entry.tool_call_id, name=entry.name, content=entry.content_dict()
                    ),
                )
            )
        elif entry.role == "assistant" and entry.tool_calls:
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=entry.content_text(),
                    tool_calls=[
                        ToolCallRequest(id=call.id, name=call.name, arguments=call.arguments or {})
                        for call in entry.tool_calls
                    ],
                )
            )
        elif entry.role in ("user", "assistant") and entry.content_text():
            messages.append(ChatMessage(role=entry.role, content=entry.content_text()))
    messages = _drop_orphaned_tool_results(messages)
    return _cap_resent_tool_history(messages)


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _run_chat(
    messages: list[ChatMessage], *, ai_settings: dict[str, Any], context: dict[str, Any]
) -> AsyncIterator[str]:
    provider = ai_settings.get("provider", "openai")
    api_key = ai_settings.get("api_key", "")
    base_url = ai_settings.get("base_url") or None
    model = ai_settings.get("model", "")
    temperature = float(ai_settings.get("temperature", 0.7) or 0.7)
    custom_prompt = ai_settings.get("system_prompt_custom") or ""

    if not api_key or not model:
        yield _sse({"type": "error", "message": "The AI assistant isn't configured yet."})
        yield _sse({"type": "done"})
        return

    try:
        client = get_ai_client(provider, api_key=api_key, base_url=base_url, model=model)
    except ValueError as exc:
        yield _sse({"type": "error", "message": str(exc)})
        yield _sse({"type": "done"})
        return

    system_prompt = _build_system_prompt(custom=custom_prompt, context=context)
    tools = registry.list_tool_specs(ai_settings=ai_settings)
    transcript = list(messages)

    for _ in range(_MAX_TOOL_ITERATIONS):
        assistant_text = ""
        tool_calls = []
        async for event in client.chat_stream(
            transcript, tools=tools, system_prompt=system_prompt, temperature=temperature
        ):
            if event.type == "token":
                assistant_text += event.text or ""
                yield _sse({"type": "token", "text": event.text})
            elif event.type == "tool_call":
                if event.tool_call is not None:
                    tool_calls.append(event.tool_call)
            elif event.type == "error":
                yield _sse({"type": "error", "message": event.text or "The AI provider returned an error."})
                yield _sse({"type": "done"})
                return
            elif event.type == "message_end":
                break

        transcript.append(ChatMessage(role="assistant", content=assistant_text or None, tool_calls=tool_calls))

        if not tool_calls:
            yield _sse({"type": "done"})
            return

        action_previewed = False
        for call in tool_calls:
            yield _sse({"type": "tool_call", "id": call.id, "tool": call.name, "arguments": call.arguments})
            yield _sse({"type": "tool_status", "tool": call.name, "status": "running"})
            dispatch_result = await registry.dispatch(call.name, call.arguments, ai_settings=ai_settings)

            if dispatch_result.kind == "result":
                yield _sse({"type": "tool_status", "tool": call.name, "status": "done"})
                tool_content = dispatch_result.result or {}
            elif dispatch_result.kind == "action_preview":
                yield _sse(
                    {
                        "type": "action_preview",
                        "action_id": dispatch_result.action_id,
                        "tool": call.name,
                        "preview": dispatch_result.preview,
                    }
                )
                tool_content = {"status": "pending_user_confirmation", "action_id": dispatch_result.action_id}
                action_previewed = True
            else:
                yield _sse(
                    {"type": "tool_status", "tool": call.name, "status": "error", "message": dispatch_result.error}
                )
                tool_content = {"error": dispatch_result.error}

            yield _sse({"type": "tool_result", "id": call.id, "tool": call.name, "content": tool_content})

            transcript.append(
                ChatMessage(
                    role="tool",
                    tool_result=ToolCallResultMessage(tool_call_id=call.id, name=call.name, content=tool_content),
                )
            )

        if action_previewed:
            # Let the model give one wrap-up reply, then stop — pass no tools
            # so there's no way for it to issue another tool call this turn;
            # the only path to actually executing the proposed action is the
            # user clicking Confirm, which calls confirm_ai_action below.
            async for event in client.chat_stream(
                transcript, tools=[], system_prompt=system_prompt, temperature=temperature
            ):
                if event.type == "token":
                    yield _sse({"type": "token", "text": event.text})
                elif event.type == "error":
                    yield _sse({"type": "error", "message": event.text or "The AI provider returned an error."})
                    break
                elif event.type == "message_end":
                    break
            yield _sse({"type": "done"})
            return

    yield _sse({"type": "done"})


@router.post("/test-connection")
async def test_ai_connection(payload: dict[str, Any], admin: dict[str, Any] = Depends(get_current_admin)):
    ai_settings = await _get_ai_settings(payload)
    provider = ai_settings.get("provider", "openai")
    api_key = ai_settings.get("api_key", "")
    base_url = ai_settings.get("base_url") or None
    model = ai_settings.get("model", "")

    if not api_key:
        return {"ok": False, "detail": None, "error": "API key is required"}
    if not model:
        return {"ok": False, "detail": None, "error": "Model is required"}

    try:
        client = get_ai_client(provider, api_key=api_key, base_url=base_url, model=model)
    except ValueError as exc:
        return {"ok": False, "detail": None, "error": str(exc)}

    ok, detail = await client.test_connection()
    if ok:
        return {"ok": True, "detail": detail, "error": None}
    return {"ok": False, "detail": None, "error": detail}


@router.post("/list-models")
async def list_ai_models(payload: dict[str, Any], admin: dict[str, Any] = Depends(get_current_admin)):
    ai_settings = await _get_ai_settings(payload)
    provider = ai_settings.get("provider", "openai")
    api_key = ai_settings.get("api_key", "")
    base_url = ai_settings.get("base_url") or None

    if not api_key:
        return {"ok": False, "models": [], "error": "API key is required"}

    try:
        # Listing models never needs a model already chosen — that's the
        # whole point, so this doesn't require `model` the way test-connection does.
        client = get_ai_client(provider, api_key=api_key, base_url=base_url, model="")
    except ValueError as exc:
        return {"ok": False, "models": [], "error": str(exc)}

    ok, models, error = await client.list_models()
    if ok:
        return {"ok": True, "models": models, "error": None}
    return {"ok": False, "models": [], "error": error}


@router.post("/chat")
async def chat(payload: ChatRequest) -> StreamingResponse:
    ai_settings = await _get_ai_settings()
    messages = _parse_messages(payload.messages)
    return StreamingResponse(
        _run_chat(messages, ai_settings=ai_settings, context=payload.context or {}), media_type="text/event-stream"
    )


@router.post("/actions/{action_id}/confirm")
async def confirm_ai_action(action_id: str) -> dict[str, Any]:
    ai_settings = await _get_ai_settings()
    result = await registry.execute_pending_action(action_id, ai_settings=ai_settings)
    if result.kind == "error":
        if result.error and result.error.endswith("is not enabled"):
            raise HTTPException(status_code=403, detail=result.error)
        if result.error == "Action not found or expired":
            raise HTTPException(status_code=404, detail=result.error)
        raise HTTPException(status_code=500, detail=result.error)
    return {"result": result.result}


@router.post("/actions/{action_id}/cancel")
async def cancel_ai_action(action_id: str) -> dict[str, Any]:
    registry.clear_pending_action(action_id)
    return {"ok": True}
