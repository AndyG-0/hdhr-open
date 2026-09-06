"""Multi-provider LLM client abstraction.

Every provider (OpenAI, Anthropic, Gemini, and any OpenAI-compatible endpoint
such as Ollama/OpenRouter/vLLM) speaks a different wire format for streaming
chat completions and tool/function calling. This module defines the
provider-agnostic shapes (`ChatMessage`, `ToolSpec`, `ToolCallRequest`,
`ToolCallResultMessage`, `StreamEvent`) and the `BaseAIClient` contract that
every provider client implements, so the rest of the backend (the tool
registry in `app.ai.tools`, the orchestration loop in `app.api.ai`) never has
to know which provider it's talking to.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass
class ToolCallRequest:
    """One tool call the model wants to make, already parsed to a dict of
    arguments — providers stream this as fragmented JSON internally, but by
    the time a `ChatMessage` or `StreamEvent` carries one, it's complete.
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ToolCallResultMessage:
    """The result of executing/dispatching a tool call, to be fed back to
    the model as the next message in the transcript.
    """

    tool_call_id: str
    name: str
    content: dict[str, Any]


@dataclass
class ChatMessage:
    """One turn in the canonical, provider-agnostic transcript.

    Exactly one of `content`, `tool_calls`, or `tool_result` is meaningful
    for a given role: `content` for "system"/"user" and plain-text
    "assistant" turns, `tool_calls` for an "assistant" turn that invoked
    tools, `tool_result` for a "tool" turn. Each provider client translates
    this into its own wire shape (see per-provider notes in the plan / each
    client module's docstring).
    """

    role: Role
    content: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)
    tool_result: ToolCallResultMessage | None = None


@dataclass
class ToolSpec:
    """A tool's JSON-schema description, as handed to the model — the
    provider-agnostic shape that `app.ai.tools.registry.list_tool_specs()`
    produces and each client converts into its own wire schema.
    """

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class StreamEvent:
    """One event yielded by `BaseAIClient.chat_stream`.

    - "token": incremental assistant text; `text` is the fragment to append.
    - "tool_call": one fully-accumulated tool call the model wants to make
      (a provider may stream several of these per turn, each keyed by its
      own `ToolCallRequest.id`); `tool_call` is set.
    - "message_end": the model's turn is complete — always the last event
      of a single `chat_stream` call, exactly once.
    - "error": the provider/network call failed; `text` carries a
      human-readable message. Terminal — no further events follow.
    """

    type: Literal["token", "tool_call", "message_end", "error"]
    text: str | None = None
    tool_call: ToolCallRequest | None = None


class BaseAIClient(ABC):
    """One instance per configured provider connection (api_key/base_url/
    model bundled at construction via `get_ai_client`), reusable across
    calls.
    """

    def __init__(self, *, api_key: str, base_url: str | None, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @abstractmethod
    async def test_connection(self) -> tuple[bool, str]:
        """Verifies the configured credentials/model work. Never raises —
        auth failures, network errors, and unknown-model errors are all
        caught internally and reported as `(False, <message>)`. Returns
        `(True, <short detail, e.g. model name/version>)` on success.
        """

    @abstractmethod
    async def list_models(self) -> tuple[bool, list[str], str]:
        """Fetches the provider's currently available model ids, live —
        keeps the settings UI's model picker from going stale the way a
        hardcoded list would as providers ship new models. Never raises —
        auth/network failures are caught internally and reported as
        `(False, [], <message>)`. Returns `(True, <model ids>, "")` on
        success. Doesn't require `self.model` to be set.
        """

    @abstractmethod
    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec],
        system_prompt: str,
        temperature: float,
    ) -> AsyncIterator[StreamEvent]:
        """Streams one assistant turn. `messages` is the full transcript so
        far (this call is stateless — no server-side conversation state).
        Yields zero or more "token"/"tool_call" events followed by exactly
        one "message_end", or a single terminal "error" event in place of
        both.
        """


def get_ai_client(provider: str, *, api_key: str, base_url: str | None, model: str) -> BaseAIClient:
    """Factory: resolves a configured provider name to a client instance.

    "openai", "ollama", and "custom" all resolve to `OpenAIClient` — Ollama,
    vLLM, LM Studio, OpenRouter, DeepSeek, and OpenAI itself all speak the
    same `/chat/completions` wire format; only `base_url` differs between
    them (and is required for anything that isn't OpenAI itself).
    """
    if provider in ("openai", "ollama", "custom"):
        from app.integrations.ai.openai_client import OpenAIClient

        return OpenAIClient(api_key=api_key, base_url=base_url, model=model)
    if provider == "anthropic":
        from app.integrations.ai.anthropic_client import AnthropicClient

        return AnthropicClient(api_key=api_key, base_url=base_url, model=model)
    if provider == "gemini":
        from app.integrations.ai.gemini_client import GeminiClient

        return GeminiClient(api_key=api_key, base_url=base_url, model=model)
    raise ValueError(f"Unknown AI provider '{provider}'")
