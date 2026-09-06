from __future__ import annotations

import json
import os

import httpx
import pytest
import respx
from httpx import Response

from app.integrations.ai import ChatMessage, ToolCallResultMessage, ToolSpec, get_ai_client
from app.integrations.ai.anthropic_client import AnthropicClient
from app.integrations.ai.gemini_client import GeminiClient
from app.integrations.ai.openai_client import OpenAIClient

# --- get_ai_client factory ---------------------------------------------------


def test_get_ai_client_routes_openai_ollama_custom_to_openai_client():
    for provider in ("openai", "ollama", "custom"):
        client = get_ai_client(provider, api_key="k", base_url=None, model="m")
        assert isinstance(client, OpenAIClient)


def test_get_ai_client_routes_anthropic():
    client = get_ai_client("anthropic", api_key="k", base_url=None, model="m")
    assert isinstance(client, AnthropicClient)


def test_get_ai_client_routes_gemini():
    client = get_ai_client("gemini", api_key="k", base_url=None, model="m")
    assert isinstance(client, GeminiClient)


def test_get_ai_client_rejects_unknown_provider():
    with pytest.raises(ValueError):
        get_ai_client("bogus", api_key="k", base_url=None, model="m")


# --- OpenAIClient -------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_openai_test_connection_ok():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": "pong"}}]})
    )
    client = OpenAIClient(api_key="k", base_url=None, model="gpt-4o-mini")

    ok, detail = await client.test_connection()

    assert ok is True
    assert "gpt-4o-mini" in detail


@pytest.mark.asyncio
@respx.mock
async def test_openai_test_connection_reports_auth_failure():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(401, json={"error": {"message": "Invalid API key"}})
    )
    client = OpenAIClient(api_key="bad", base_url=None, model="gpt-4o-mini")

    ok, detail = await client.test_connection()

    assert ok is False
    assert "Invalid API key" in detail


@pytest.mark.asyncio
@respx.mock
async def test_openai_test_connection_never_raises_on_network_error():
    respx.post("https://api.openai.com/v1/chat/completions").mock(side_effect=httpx.ConnectError("boom"))
    client = OpenAIClient(api_key="k", base_url=None, model="gpt-4o-mini")

    ok, detail = await client.test_connection()

    assert ok is False
    assert "Connection failed" in detail


@pytest.mark.asyncio
@respx.mock
async def test_openai_list_models_filters_out_non_chat_models():
    respx.get("https://api.openai.com/v1/models").mock(
        return_value=Response(
            200,
            json={
                "data": [
                    {"id": "gpt-4o"},
                    {"id": "gpt-4.1-mini"},
                    {"id": "text-embedding-3-small"},
                    {"id": "whisper-1"},
                    {"id": "dall-e-3"},
                ]
            },
        )
    )
    client = OpenAIClient(api_key="k", base_url=None, model="")

    ok, models, error = await client.list_models()

    assert ok is True
    assert models == ["gpt-4.1-mini", "gpt-4o"]
    assert error == ""


@pytest.mark.asyncio
@respx.mock
async def test_openai_list_models_reports_auth_failure():
    respx.get("https://api.openai.com/v1/models").mock(
        return_value=Response(401, json={"error": {"message": "Invalid API key"}})
    )
    client = OpenAIClient(api_key="bad", base_url=None, model="")

    ok, models, error = await client.list_models()

    assert ok is False
    assert models == []
    assert "Invalid API key" in error


@pytest.mark.asyncio
@respx.mock
async def test_openai_list_models_never_raises_on_network_error():
    respx.get("https://api.openai.com/v1/models").mock(side_effect=httpx.ConnectError("boom"))
    client = OpenAIClient(api_key="k", base_url=None, model="")

    ok, models, error = await client.list_models()

    assert ok is False
    assert models == []
    assert "Connection failed" in error


@pytest.mark.asyncio
@respx.mock
async def test_openai_chat_stream_yields_tokens_then_message_end():
    body = (
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(200, content=body, headers={"content-type": "text/event-stream"})
    )
    client = OpenAIClient(api_key="k", base_url=None, model="gpt-4o-mini")

    events = [
        e
        async for e in client.chat_stream(
            [ChatMessage(role="user", content="hi")], tools=[], system_prompt="", temperature=0.7
        )
    ]

    assert [e.type for e in events] == ["token", "token", "message_end"]
    assert events[0].text == "Hello"
    assert events[1].text == " world"


@pytest.mark.asyncio
@respx.mock
async def test_openai_chat_stream_accumulates_fragmented_tool_call():
    body = (
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1",'
        b'"function":{"name":"search_guide","arguments":""}}]}}]}\n\n'
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{\\"query\\""}}]}}]}\n\n'
        b'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":": \\"office\\"}"}}]}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(200, content=body, headers={"content-type": "text/event-stream"})
    )
    client = OpenAIClient(api_key="k", base_url=None, model="gpt-4o-mini")

    events = [
        e
        async for e in client.chat_stream(
            [ChatMessage(role="user", content="hi")], tools=[], system_prompt="", temperature=0.7
        )
    ]

    tool_events = [e for e in events if e.type == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0].tool_call.id == "call_1"
    assert tool_events[0].tool_call.name == "search_guide"
    assert tool_events[0].tool_call.arguments == {"query": "office"}
    assert events[-1].type == "message_end"


@pytest.mark.asyncio
@respx.mock
async def test_openai_chat_stream_yields_error_event_on_bad_status():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(500, json={"error": {"message": "server exploded"}})
    )
    client = OpenAIClient(api_key="k", base_url=None, model="gpt-4o-mini")

    events = [
        e
        async for e in client.chat_stream(
            [ChatMessage(role="user", content="hi")], tools=[], system_prompt="", temperature=0.7
        )
    ]

    assert len(events) == 1
    assert events[0].type == "error"
    assert "server exploded" in events[0].text


@pytest.mark.asyncio
@respx.mock
async def test_openai_chat_stream_retries_without_reasoning_effort_when_tools_conflict():
    route = respx.post("https://api.openai.com/v1/chat/completions")
    route.side_effect = [
        Response(
            400,
            json={
                "error": {
                    "message": (
                        "Function tools with reasoning_effort are not supported for gpt-5.6-luna in "
                        "/v1/chat/completions. To use function tools, use /v1/responses or set "
                        "reasoning_effort to 'none'."
                    )
                }
            },
        ),
        Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        ),
    ]
    tools = [ToolSpec(name="search_guide", description="d", parameters={})]
    client = OpenAIClient(api_key="k", base_url=None, model="gpt-5.6-luna")

    events = [
        e
        async for e in client.chat_stream(
            [ChatMessage(role="user", content="hi")], tools=tools, system_prompt="", temperature=0.7
        )
    ]

    assert [e.type for e in events] == ["token", "message_end"]
    assert events[0].text == "Hello"
    assert route.call_count == 2
    retried_body = json.loads(route.calls[1].request.content)
    assert retried_body["reasoning_effort"] == "none"


@pytest.mark.asyncio
@respx.mock
async def test_openai_chat_stream_retries_without_temperature_when_unsupported():
    route = respx.post("https://api.openai.com/v1/chat/completions")
    route.side_effect = [
        Response(
            400,
            json={
                "error": {
                    "message": (
                        "Unsupported value: 'temperature' does not support 0.7 with this model. "
                        "Only the default (1) value is supported."
                    )
                }
            },
        ),
        Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\ndata: [DONE]\n\n',
            headers={"content-type": "text/event-stream"},
        ),
    ]
    client = OpenAIClient(api_key="k", base_url=None, model="gpt-5.6-luna")

    events = [
        e
        async for e in client.chat_stream(
            [ChatMessage(role="user", content="hi")], tools=[], system_prompt="", temperature=0.7
        )
    ]

    assert [e.type for e in events] == ["token", "message_end"]
    assert events[0].text == "Hello"
    assert route.call_count == 2
    retried_body = json.loads(route.calls[1].request.content)
    assert "temperature" not in retried_body


@pytest.mark.asyncio
@respx.mock
async def test_openai_chat_stream_does_not_retry_unrelated_bad_status():
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(500, json={"error": {"message": "server exploded"}})
    )
    tools = [ToolSpec(name="search_guide", description="d", parameters={})]
    client = OpenAIClient(api_key="k", base_url=None, model="gpt-4o-mini")

    events = [
        e
        async for e in client.chat_stream(
            [ChatMessage(role="user", content="hi")], tools=tools, system_prompt="", temperature=0.7
        )
    ]

    assert len(events) == 1
    assert events[0].type == "error"
    assert "server exploded" in events[0].text


def test_openai_wire_includes_tools_and_tool_result():
    from app.integrations.ai.openai_client import _to_wire_messages, _to_wire_tools

    messages = [
        ChatMessage(role="user", content="what's on?"),
        ChatMessage(
            role="tool",
            tool_result=ToolCallResultMessage(tool_call_id="call_1", name="search_guide", content={"ok": True}),
        ),
    ]
    wire = _to_wire_messages(messages, system_prompt="be helpful")
    assert wire[0] == {"role": "system", "content": "be helpful"}
    assert wire[-1]["role"] == "tool"
    assert wire[-1]["tool_call_id"] == "call_1"

    tools = _to_wire_tools([ToolSpec(name="search_guide", description="d", parameters={"type": "object"})])
    assert tools[0]["function"]["name"] == "search_guide"


# --- AnthropicClient ------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_anthropic_test_connection_ok():
    respx.post("https://api.anthropic.com/v1/messages").mock(return_value=Response(200, json={"content": []}))
    client = AnthropicClient(api_key="k", base_url=None, model="claude-sonnet-5")

    ok, detail = await client.test_connection()

    assert ok is True
    assert "claude-sonnet-5" in detail


@pytest.mark.asyncio
@respx.mock
async def test_anthropic_test_connection_reports_auth_failure():
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(401, json={"error": {"message": "authentication_error"}})
    )
    client = AnthropicClient(api_key="bad", base_url=None, model="claude-sonnet-5")

    ok, detail = await client.test_connection()

    assert ok is False
    assert "authentication_error" in detail


@pytest.mark.asyncio
@respx.mock
async def test_anthropic_list_models_preserves_api_order():
    respx.get("https://api.anthropic.com/v1/models").mock(
        return_value=Response(
            200,
            json={"data": [{"id": "claude-sonnet-5"}, {"id": "claude-opus-5"}, {"id": "claude-3-5-sonnet"}]},
        )
    )
    client = AnthropicClient(api_key="k", base_url=None, model="")

    ok, models, error = await client.list_models()

    assert ok is True
    assert models == ["claude-sonnet-5", "claude-opus-5", "claude-3-5-sonnet"]
    assert error == ""


@pytest.mark.asyncio
@respx.mock
async def test_anthropic_list_models_reports_failure():
    respx.get("https://api.anthropic.com/v1/models").mock(
        return_value=Response(401, json={"error": {"message": "authentication_error"}})
    )
    client = AnthropicClient(api_key="bad", base_url=None, model="")

    ok, models, error = await client.list_models()

    assert ok is False
    assert models == []
    assert "authentication_error" in error


@pytest.mark.asyncio
@respx.mock
async def test_anthropic_chat_stream_yields_text_and_tool_use():
    body = (
        b'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
        b'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hello"}}\n\n'
        b'data: {"type":"content_block_stop","index":0}\n\n'
        b'data: {"type":"content_block_start","index":1,"content_block":'
        b'{"type":"tool_use","id":"toolu_1","name":"search_guide","input":{}}}\n\n'
        b'data: {"type":"content_block_delta","index":1,"delta":'
        b'{"type":"input_json_delta","partial_json":"{\\"query\\": \\"office\\"}"}}\n\n'
        b'data: {"type":"content_block_stop","index":1}\n\n'
        b'data: {"type":"message_stop"}\n\n'
    )
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(200, content=body, headers={"content-type": "text/event-stream"})
    )
    client = AnthropicClient(api_key="k", base_url=None, model="claude-sonnet-5")

    events = [
        e
        async for e in client.chat_stream(
            [ChatMessage(role="user", content="hi")], tools=[], system_prompt="sys", temperature=0.5
        )
    ]

    assert events[0].type == "token"
    assert events[0].text == "Hello"
    tool_events = [e for e in events if e.type == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0].tool_call.id == "toolu_1"
    assert tool_events[0].tool_call.name == "search_guide"
    assert tool_events[0].tool_call.arguments == {"query": "office"}
    assert events[-1].type == "message_end"


# --- GeminiClient ---------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_gemini_test_connection_ok():
    respx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent").mock(
        return_value=Response(200, json={"candidates": []})
    )
    client = GeminiClient(api_key="k", base_url=None, model="gemini-2.0-flash")

    ok, detail = await client.test_connection()

    assert ok is True
    assert "gemini-2.0-flash" in detail


@pytest.mark.asyncio
@respx.mock
async def test_gemini_test_connection_reports_failure():
    respx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent").mock(
        return_value=Response(400, json={"error": {"message": "API key not valid"}})
    )
    client = GeminiClient(api_key="bad", base_url=None, model="gemini-2.0-flash")

    ok, detail = await client.test_connection()

    assert ok is False
    assert "API key not valid" in detail


@pytest.mark.asyncio
@respx.mock
async def test_gemini_list_models_filters_by_generate_content_capability():
    respx.get("https://generativelanguage.googleapis.com/v1beta/models").mock(
        return_value=Response(
            200,
            json={
                "models": [
                    {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/gemini-1.5-pro", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
                ]
            },
        )
    )
    client = GeminiClient(api_key="k", base_url=None, model="")

    ok, models, error = await client.list_models()

    assert ok is True
    assert models == ["gemini-1.5-pro", "gemini-2.0-flash"]
    assert error == ""


@pytest.mark.asyncio
@respx.mock
async def test_gemini_list_models_reports_failure():
    respx.get("https://generativelanguage.googleapis.com/v1beta/models").mock(
        return_value=Response(400, json={"error": {"message": "API key not valid"}})
    )
    client = GeminiClient(api_key="bad", base_url=None, model="")

    ok, models, error = await client.list_models()

    assert ok is False
    assert models == []
    assert "API key not valid" in error


@pytest.mark.asyncio
@respx.mock
async def test_gemini_chat_stream_yields_text_and_function_call():
    body = (
        b'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}],"role":"model"}}]}\n\n'
        b'data: {"candidates":[{"content":{"parts":[{"functionCall":'
        b'{"name":"search_guide","args":{"query":"office"}}}],"role":"model"}}]}\n\n'
    )
    respx.post("https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:streamGenerateContent").mock(
        return_value=Response(200, content=body, headers={"content-type": "text/event-stream"})
    )
    client = GeminiClient(api_key="k", base_url=None, model="gemini-2.0-flash")

    events = [
        e
        async for e in client.chat_stream(
            [ChatMessage(role="user", content="hi")], tools=[], system_prompt="sys", temperature=0.5
        )
    ]

    assert events[0].type == "token"
    assert events[0].text == "Hello"
    tool_events = [e for e in events if e.type == "tool_call"]
    assert len(tool_events) == 1
    assert tool_events[0].tool_call.name == "search_guide"
    assert tool_events[0].tool_call.arguments == {"query": "office"}
    assert tool_events[0].tool_call.id  # synthesized, just needs to be non-empty
    assert events[-1].type == "message_end"


# --- Manual, real-provider smoke test (not part of default suite) --------------


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="requires a real OPENAI_API_KEY")
@pytest.mark.asyncio
async def test_openai_real_test_connection_smoke():
    client = OpenAIClient(api_key=os.environ["OPENAI_API_KEY"], base_url=None, model="gpt-4o-mini")
    ok, detail = await client.test_connection()
    assert ok is True, detail
