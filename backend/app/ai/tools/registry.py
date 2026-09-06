"""Tool-calling registry: JSON-schema tool specs handed to the LLM, and the
`dispatch()` entry point that turns a model-issued tool call into either an
immediate result (read-only tools) or a cached, user-confirmable preview
(mutating tools).

Mutating tools are never executed from here — `dispatch()` only ever calls a
mutating tool's `preview`. Its `execute` callable exists solely for
`app.api.ai`'s `POST /api/ai/actions/{action_id}/confirm` endpoint to call,
after a human has explicitly approved that specific action. This module has
no reference to any mutating tool's `execute` at all, by construction — the
only path to `execute` runs through the confirm endpoint, so no bug in the
chat orchestration loop can make an LLM's tool call mutate anything without
a human in the loop.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from app.integrations.ai import ToolSpec
from app.storage.cache import cache

logger = logging.getLogger(__name__)

# Pending mutating-tool previews live here for 10 minutes — long enough for
# a user to notice the chat drawer's confirmation card and click, short
# enough that a stale/abandoned one doesn't linger and doesn't need its own
# persistent store (this reuses the app's existing single-process TTLCache,
# same as `tuner_allocator`'s in-memory assumptions elsewhere).
_ACTION_TTL_SECONDS = 600
_ACTION_CACHE_PREFIX = "ai_action:"

Handler = Callable[..., Awaitable[dict[str, Any]]]


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    mutating: bool = False
    requires_permission: str | None = None
    handler: Handler | None = None  # read-only tools: handler(**args) -> dict
    preview: Handler | None = None  # mutating tools: preview(**args) -> dict (no side effects)
    execute: Handler | None = None  # mutating tools: execute(**args) -> dict; only ever called by the confirm endpoint

    def __post_init__(self) -> None:
        if self.mutating:
            if self.preview is None or self.execute is None:
                raise ValueError(f"Mutating tool '{self.name}' needs both preview and execute")
        elif self.handler is None:
            raise ValueError(f"Non-mutating tool '{self.name}' needs a handler")


TOOL_REGISTRY: dict[str, ToolDefinition] = {}


def register(tool: ToolDefinition) -> None:
    TOOL_REGISTRY[tool.name] = tool


def _tool_enabled(tool: ToolDefinition, ai_settings: dict[str, Any]) -> bool:
    if tool.requires_permission is None:
        return True
    return bool(ai_settings.get(tool.requires_permission))


def list_tool_specs(*, ai_settings: dict[str, Any]) -> list[ToolSpec]:
    """Tools gated by an unsatisfied `requires_permission` are excluded
    entirely — the model is never even told they exist, so it can't try to
    call (or talk a user into enabling) something it has no business using.
    """
    return [
        ToolSpec(name=t.name, description=t.description, parameters=t.parameters)
        for t in TOOL_REGISTRY.values()
        if _tool_enabled(t, ai_settings)
    ]


@dataclass
class ToolDispatchResult:
    kind: Literal["result", "action_preview", "error"]
    result: dict[str, Any] | None = None
    action_id: str | None = None
    preview: dict[str, Any] | None = None
    error: str | None = None


def _action_cache_key(action_id: str) -> str:
    return f"{_ACTION_CACHE_PREFIX}{action_id}"


async def dispatch(name: str, arguments: dict[str, Any], *, ai_settings: dict[str, Any]) -> ToolDispatchResult:
    tool = TOOL_REGISTRY.get(name)
    if tool is None:
        return ToolDispatchResult(kind="error", error=f"Unknown tool '{name}'")
    if not _tool_enabled(tool, ai_settings):
        return ToolDispatchResult(kind="error", error=f"Tool '{name}' is not enabled")

    if not tool.mutating:
        assert tool.handler is not None
        try:
            result = await tool.handler(**arguments)
        except Exception as exc:
            logger.warning("Tool '%s' handler failed: %s", name, exc, exc_info=True)
            return ToolDispatchResult(kind="error", error=str(exc))
        return ToolDispatchResult(kind="result", result=result)

    assert tool.preview is not None
    try:
        preview = await tool.preview(**arguments)
    except Exception as exc:
        logger.warning("Tool '%s' preview failed: %s", name, exc, exc_info=True)
        return ToolDispatchResult(kind="error", error=str(exc))

    action_id = uuid.uuid4().hex
    cache.set(
        _action_cache_key(action_id),
        {"tool": name, "arguments": arguments, "preview": preview},
        _ACTION_TTL_SECONDS,
    )
    return ToolDispatchResult(kind="action_preview", action_id=action_id, preview=preview)


def get_pending_action(action_id: str) -> dict[str, Any] | None:
    return cache.get(_action_cache_key(action_id))


def clear_pending_action(action_id: str) -> None:
    cache.delete(_action_cache_key(action_id))


async def execute_pending_action(action_id: str, *, ai_settings: dict[str, Any]) -> ToolDispatchResult:
    """Consume-once execution of a previously-previewed mutating tool call.

    Only ever called by `app.api.ai`'s confirm endpoint — never by the chat
    orchestration loop. Deletes the cache entry *before* executing so a
    double-click or replayed request can't double-execute (e.g. schedule the
    same recording twice); re-checks `requires_permission` against the
    *current* settings, not the settings at propose-time, since they could
    have changed in between.
    """
    pending = get_pending_action(action_id)
    if pending is None:
        return ToolDispatchResult(kind="error", error="Action not found or expired")

    tool = TOOL_REGISTRY.get(pending["tool"])
    if tool is None or not tool.mutating or tool.execute is None:
        return ToolDispatchResult(kind="error", error=f"Unknown or non-mutating tool '{pending['tool']}'")
    if not _tool_enabled(tool, ai_settings):
        clear_pending_action(action_id)
        return ToolDispatchResult(kind="error", error=f"Tool '{tool.name}' is not enabled")

    clear_pending_action(action_id)
    try:
        result = await tool.execute(**pending["arguments"])
    except Exception as exc:
        logger.warning("Tool '%s' execute failed: %s", tool.name, exc, exc_info=True)
        return ToolDispatchResult(kind="error", error=str(exc))
    return ToolDispatchResult(kind="result", result=result)
