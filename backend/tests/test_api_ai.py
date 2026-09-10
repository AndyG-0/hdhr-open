from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.tools import registry
from app.api import ai as ai_api
from app.auth import get_current_user
from app.integrations.ai import BaseAIClient, StreamEvent, ToolCallRequest
from app.storage import db


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(ai_api.router)
    return app


@pytest.fixture
def admin_client():
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "admin", "role": "admin"}
    return TestClient(app)


@pytest.fixture
def member_client():
    app = _app()
    app.dependency_overrides[get_current_user] = lambda: {"id": "member", "role": "member"}
    return TestClient(app)


@pytest.fixture
def unauthenticated_client():
    return TestClient(_app())


class _FakeClient(BaseAIClient):
    def __init__(self, *, ok: bool, detail: str, models: list[str] | None = None, **kwargs):
        super().__init__(api_key="k", base_url=None, model="m")
        self._ok = ok
        self._detail = detail
        self._models = models or []

    async def test_connection(self):
        return self._ok, self._detail

    async def list_models(self):
        return self._ok, self._models, ("" if self._ok else self._detail)

    def chat_stream(self, *args, **kwargs):
        raise NotImplementedError


class _ScriptedClient(BaseAIClient):
    """A fake provider client whose `chat_stream` returns one scripted list
    of `StreamEvent`s per call, in order — lets a test script an entire
    multi-turn tool-calling conversation without touching real wire parsing.
    """

    def __init__(self, *, turns: list[list[StreamEvent]]):
        super().__init__(api_key="k", base_url=None, model="m")
        self._turns = list(turns)
        self.calls: list[dict[str, Any]] = []

    async def test_connection(self):
        return True, "ok"

    async def list_models(self):
        return True, [], ""

    async def chat_stream(self, messages, *, tools, system_prompt, temperature):
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        for event in self._turns.pop(0):
            yield event


def _save_ai_settings(*, enable_recording_tools: bool = False) -> None:
    db.save_network_integration(
        "ai",
        "ai",
        "AI Assistant",
        {
            "provider": "openai",
            "api_key": "test-key",
            "base_url": "",
            "model": "gpt-4o-mini",
            "system_prompt_custom": "",
            "temperature": 0.7,
            "enable_recording_tools": enable_recording_tools,
        },
    )


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block:
            continue
        assert block.startswith("data: ")
        events.append(json.loads(block[len("data: ") :]))
    return events


def test_test_connection_requires_login(unauthenticated_client, tmp_db):
    response = unauthenticated_client.post("/api/ai/test-connection", json={})
    assert response.status_code == 401


def test_test_connection_requires_admin(member_client, tmp_db):
    response = member_client.post("/api/ai/test-connection", json={})
    assert response.status_code == 403


def test_test_connection_missing_api_key(admin_client, tmp_db):
    response = admin_client.post("/api/ai/test-connection", json={"provider": "openai", "model": "gpt-4o-mini"})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "detail": None, "error": "API key is required"}


def test_test_connection_missing_model(admin_client, tmp_db):
    response = admin_client.post("/api/ai/test-connection", json={"provider": "openai", "api_key": "k"})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "detail": None, "error": "Model is required"}


def test_test_connection_unknown_provider(admin_client, tmp_db):
    response = admin_client.post("/api/ai/test-connection", json={"provider": "bogus", "api_key": "k", "model": "m"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "Unknown AI provider" in body["error"]


def test_test_connection_ok(admin_client, tmp_db, monkeypatch):
    monkeypatch.setattr(
        ai_api, "get_ai_client", lambda *a, **kw: _FakeClient(ok=True, detail="Connected (model: gpt-4o-mini)")
    )

    response = admin_client.post(
        "/api/ai/test-connection", json={"provider": "openai", "api_key": "k", "model": "gpt-4o-mini"}
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "detail": "Connected (model: gpt-4o-mini)", "error": None}


def test_test_connection_reports_failure(admin_client, tmp_db, monkeypatch):
    monkeypatch.setattr(
        ai_api, "get_ai_client", lambda *a, **kw: _FakeClient(ok=False, detail="HTTP 401: Invalid API key")
    )

    response = admin_client.post(
        "/api/ai/test-connection", json={"provider": "openai", "api_key": "bad", "model": "gpt-4o-mini"}
    )

    assert response.status_code == 200
    assert response.json() == {"ok": False, "detail": None, "error": "HTTP 401: Invalid API key"}


def test_test_connection_uses_payload_override_onto_saved_settings(admin_client, tmp_db, monkeypatch):
    db.save_network_integration(
        "ai",
        "ai",
        "AI Assistant",
        {
            "provider": "openai",
            "api_key": "saved-key",
            "base_url": "",
            "model": "old-model",
            "system_prompt_custom": "",
            "temperature": 0.7,
            "enable_recording_tools": False,
        },
    )
    captured: dict[str, object] = {}

    def fake_get_ai_client(provider, *, api_key, base_url, model):
        captured.update({"provider": provider, "api_key": api_key, "base_url": base_url, "model": model})
        return _FakeClient(ok=True, detail="ok")

    monkeypatch.setattr(ai_api, "get_ai_client", fake_get_ai_client)

    response = admin_client.post("/api/ai/test-connection", json={"model": "new-model"})

    assert response.status_code == 200
    assert captured["api_key"] == "saved-key"
    assert captured["model"] == "new-model"


# --- /list-models --------------------------------------------------------------


def test_list_models_requires_login(unauthenticated_client, tmp_db):
    response = unauthenticated_client.post("/api/ai/list-models", json={})
    assert response.status_code == 401


def test_list_models_requires_admin(member_client, tmp_db):
    response = member_client.post("/api/ai/list-models", json={})
    assert response.status_code == 403


def test_list_models_missing_api_key(admin_client, tmp_db):
    response = admin_client.post("/api/ai/list-models", json={"provider": "openai"})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "models": [], "error": "API key is required"}


def test_list_models_unknown_provider(admin_client, tmp_db):
    response = admin_client.post("/api/ai/list-models", json={"provider": "bogus", "api_key": "k"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "Unknown AI provider" in body["error"]


def test_list_models_ok(admin_client, tmp_db, monkeypatch):
    monkeypatch.setattr(
        ai_api, "get_ai_client", lambda *a, **kw: _FakeClient(ok=True, detail="", models=["gpt-4o", "gpt-4o-mini"])
    )

    response = admin_client.post("/api/ai/list-models", json={"provider": "openai", "api_key": "k"})

    assert response.status_code == 200
    assert response.json() == {"ok": True, "models": ["gpt-4o", "gpt-4o-mini"], "error": None}


def test_list_models_reports_failure(admin_client, tmp_db, monkeypatch):
    monkeypatch.setattr(
        ai_api, "get_ai_client", lambda *a, **kw: _FakeClient(ok=False, detail="HTTP 401: Invalid API key")
    )

    response = admin_client.post("/api/ai/list-models", json={"provider": "openai", "api_key": "bad"})

    assert response.status_code == 200
    assert response.json() == {"ok": False, "models": [], "error": "HTTP 401: Invalid API key"}


# --- /chat -------------------------------------------------------------------


def test_chat_requires_login(unauthenticated_client, tmp_db):
    response = unauthenticated_client.post("/api/ai/chat", json={"messages": []})
    assert response.status_code == 401


def test_chat_streams_tokens_and_done_when_no_tool_calls(admin_client, tmp_db, monkeypatch):
    _save_ai_settings()
    fake = _ScriptedClient(
        turns=[
            [
                StreamEvent(type="token", text="Hi "),
                StreamEvent(type="token", text="there!"),
                StreamEvent(type="message_end"),
            ]
        ]
    )
    monkeypatch.setattr(ai_api, "get_ai_client", lambda *a, **kw: fake)

    response = admin_client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "hello"}]})

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events == [
        {"type": "token", "text": "Hi "},
        {"type": "token", "text": "there!"},
        {"type": "done"},
    ]
    assert len(fake.calls) == 1


def test_chat_not_configured_yields_error_then_done(admin_client, tmp_db):
    response = admin_client.post("/api/ai/chat", json={"messages": []})

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[0]["type"] == "error"
    assert events[-1] == {"type": "done"}


def test_chat_action_preview_ends_loop_after_one_wrapup_reply(admin_client, tmp_db, monkeypatch):
    _save_ai_settings(enable_recording_tools=True)

    async def fake_preview(**kwargs):
        return {"title": "Fake Show", "channel": kwargs.get("channel")}

    executed = {"called": False}

    async def fake_execute(**kwargs):
        executed["called"] = True
        return {"status": "scheduled"}

    monkeypatch.setattr(registry.TOOL_REGISTRY["schedule_recording"], "preview", fake_preview)
    monkeypatch.setattr(registry.TOOL_REGISTRY["schedule_recording"], "execute", fake_execute)

    fake = _ScriptedClient(
        turns=[
            [
                StreamEvent(type="token", text="Let me check..."),
                StreamEvent(
                    type="tool_call",
                    tool_call=ToolCallRequest(id="call_1", name="schedule_recording", arguments={"channel": "5.1"}),
                ),
                StreamEvent(type="message_end"),
            ],
            [StreamEvent(type="token", text="I've proposed that for you."), StreamEvent(type="message_end")],
        ]
    )
    monkeypatch.setattr(ai_api, "get_ai_client", lambda *a, **kw: fake)

    response = admin_client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "record it"}]})

    assert response.status_code == 200
    events = _parse_sse(response.text)
    kinds = [e["type"] for e in events]
    assert kinds == ["token", "tool_call", "tool_status", "action_preview", "tool_result", "token", "done"]
    action_event = next(e for e in events if e["type"] == "action_preview")
    assert action_event["tool"] == "schedule_recording"
    assert action_event["preview"]["title"] == "Fake Show"
    assert executed["called"] is False
    assert len(fake.calls) == 2  # the initial turn, plus the wrap-up reply


def test_chat_accepts_legacy_plain_text_only_payload(admin_client, tmp_db, monkeypatch):
    _save_ai_settings()
    fake = _ScriptedClient(turns=[[StreamEvent(type="token", text="hi"), StreamEvent(type="message_end")]])
    monkeypatch.setattr(ai_api, "get_ai_client", lambda *a, **kw: fake)

    response = admin_client.post(
        "/api/ai/chat",
        json={
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
                {"role": "user", "content": "again"},
            ]
        },
    )

    assert response.status_code == 200
    assert _parse_sse(response.text)[-1] == {"type": "done"}
    assert [m.role for m in fake.calls[0]["messages"]] == ["user", "assistant", "user"]


def test_parse_messages_reconstructs_tool_history():
    messages = ai_api._parse_messages(
        [
            ai_api.WireMessage(role="user", content="find college football"),
            ai_api.WireMessage(
                role="assistant",
                content="Here are the games I found.",
                tool_calls=[ai_api.WireToolCall(id="call_1", name="search_guide", arguments={"query": "football"})],
            ),
            ai_api.WireMessage(
                role="tool",
                tool_call_id="call_1",
                name="search_guide",
                content={"results": [{"title": "Alabama at Georgia"}], "total_matches": 1},
            ),
            ai_api.WireMessage(role="user", content="all of those games"),
        ]
    )

    assert [m.role for m in messages] == ["user", "assistant", "tool", "user"]
    assert messages[1].tool_calls == [
        ToolCallRequest(id="call_1", name="search_guide", arguments={"query": "football"})
    ]
    assert messages[2].tool_result.tool_call_id == "call_1"
    assert messages[2].tool_result.content == {"results": [{"title": "Alabama at Georgia"}], "total_matches": 1}


def test_chat_forwards_resent_tool_history_to_provider(admin_client, tmp_db, monkeypatch):
    _save_ai_settings()
    fake = _ScriptedClient(
        turns=[[StreamEvent(type="token", text="Scheduling those now."), StreamEvent(type="message_end")]]
    )
    monkeypatch.setattr(ai_api, "get_ai_client", lambda *a, **kw: fake)

    response = admin_client.post(
        "/api/ai/chat",
        json={
            "messages": [
                {"role": "user", "content": "find college football games"},
                {
                    "role": "assistant",
                    "content": "Here are the games I found.",
                    "tool_calls": [{"id": "call_1", "name": "search_guide", "arguments": {"query": "football"}}],
                },
                {
                    "role": "tool",
                    "tool_call_id": "call_1",
                    "name": "search_guide",
                    "content": {"results": [{"channel_number": "5.1", "start": 123}], "total_matches": 1},
                },
                {"role": "user", "content": "all of those games"},
            ]
        },
    )

    assert response.status_code == 200
    forwarded = fake.calls[0]["messages"]
    assert [m.role for m in forwarded] == ["user", "assistant", "tool", "user"]
    assert forwarded[1].tool_calls[0].name == "search_guide"
    assert forwarded[2].tool_result.content["results"][0]["channel_number"] == "5.1"


def test_chat_drops_orphaned_tool_result(admin_client, tmp_db, monkeypatch):
    _save_ai_settings()
    fake = _ScriptedClient(turns=[[StreamEvent(type="token", text="ok"), StreamEvent(type="message_end")]])
    monkeypatch.setattr(ai_api, "get_ai_client", lambda *a, **kw: fake)

    response = admin_client.post(
        "/api/ai/chat",
        json={
            "messages": [
                {"role": "user", "content": "hello"},
                # No preceding assistant tool_calls entry for this id — must be dropped.
                {
                    "role": "tool",
                    "tool_call_id": "call_orphan",
                    "name": "search_guide",
                    "content": {"results": []},
                },
                {"role": "user", "content": "again"},
            ]
        },
    )

    assert response.status_code == 200
    forwarded = fake.calls[0]["messages"]
    assert [m.role for m in forwarded] == ["user", "user"]


def test_chat_emits_tool_call_and_tool_result_events(admin_client, tmp_db, monkeypatch):
    _save_ai_settings()
    fake = _ScriptedClient(
        turns=[
            [
                StreamEvent(
                    type="tool_call",
                    tool_call=ToolCallRequest(id="call_1", name="get_channel_lineup", arguments={}),
                ),
                StreamEvent(type="message_end"),
            ],
            [StreamEvent(type="token", text="Done."), StreamEvent(type="message_end")],
        ]
    )
    monkeypatch.setattr(ai_api, "get_ai_client", lambda *a, **kw: fake)

    response = admin_client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "what's on"}]})

    assert response.status_code == 200
    events = _parse_sse(response.text)
    tool_call_event = next(e for e in events if e["type"] == "tool_call")
    assert tool_call_event == {"type": "tool_call", "id": "call_1", "tool": "get_channel_lineup", "arguments": {}}
    tool_result_event = next(e for e in events if e["type"] == "tool_result")
    assert tool_result_event["id"] == "call_1"
    assert tool_result_event["tool"] == "get_channel_lineup"
    assert "content" in tool_result_event


def test_chat_caps_resent_tool_history_length():
    raw = [ai_api.WireMessage(role="user", content="start")]
    for i in range(5):
        raw.append(
            ai_api.WireMessage(
                role="assistant",
                content=f"turn {i} summary",
                tool_calls=[ai_api.WireToolCall(id=f"call_{i}", name="search_guide", arguments={"query": str(i)})],
            )
        )
        raw.append(
            ai_api.WireMessage(role="tool", tool_call_id=f"call_{i}", name="search_guide", content={"n": i})
        )

    messages = ai_api._parse_messages(raw)

    tool_call_entries = [m for m in messages if m.role == "assistant" and m.tool_calls]
    assert len(tool_call_entries) == ai_api._MAX_RESENT_TOOL_EXCHANGES
    assert [c.tool_calls[0].id for c in tool_call_entries] == ["call_2", "call_3", "call_4"]
    # The stale exchanges (0, 1) are collapsed to plain assistant text, not dropped entirely.
    stale_text_entries = [m for m in messages if m.role == "assistant" and not m.tool_calls]
    assert [m.content for m in stale_text_entries] == ["turn 0 summary", "turn 1 summary"]
    # Their tool results are gone.
    tool_result_ids = [m.tool_result.tool_call_id for m in messages if m.role == "tool"]
    assert tool_result_ids == ["call_2", "call_3", "call_4"]


def test_chat_hard_caps_tool_iterations(admin_client, tmp_db, monkeypatch):
    _save_ai_settings()
    turn = [
        StreamEvent(
            type="tool_call",
            tool_call=ToolCallRequest(id="call_x", name="get_channel_lineup", arguments={}),
        ),
        StreamEvent(type="message_end"),
    ]
    fake = _ScriptedClient(turns=[list(turn) for _ in range(6)])
    monkeypatch.setattr(ai_api, "get_ai_client", lambda *a, **kw: fake)

    response = admin_client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "loop forever"}]})

    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert events[-1] == {"type": "done"}
    assert len(fake.calls) == 6


# --- confirm / cancel ----------------------------------------------------------


def _propose_schedule_recording_action(
    admin_client, monkeypatch, *, enable_recording_tools: bool = True
) -> tuple[str, dict]:
    _save_ai_settings(enable_recording_tools=enable_recording_tools)

    async def fake_preview(**kwargs):
        return {"title": "Fake Show"}

    executed = {"called": False}

    async def fake_execute(**kwargs):
        executed["called"] = True
        return {"status": "scheduled"}

    monkeypatch.setattr(registry.TOOL_REGISTRY["schedule_recording"], "preview", fake_preview)
    monkeypatch.setattr(registry.TOOL_REGISTRY["schedule_recording"], "execute", fake_execute)

    fake = _ScriptedClient(
        turns=[
            [
                StreamEvent(
                    type="tool_call",
                    tool_call=ToolCallRequest(id="call_1", name="schedule_recording", arguments={"channel": "5.1"}),
                ),
                StreamEvent(type="message_end"),
            ],
            [StreamEvent(type="message_end")],
        ]
    )
    monkeypatch.setattr(ai_api, "get_ai_client", lambda *a, **kw: fake)

    response = admin_client.post("/api/ai/chat", json={"messages": [{"role": "user", "content": "record it"}]})
    events = _parse_sse(response.text)
    action_event = next(e for e in events if e["type"] == "action_preview")
    return action_event["action_id"], executed


def test_confirm_requires_login(unauthenticated_client, tmp_db):
    response = unauthenticated_client.post("/api/ai/actions/whatever/confirm")
    assert response.status_code == 401


def test_cancel_requires_login(unauthenticated_client, tmp_db):
    response = unauthenticated_client.post("/api/ai/actions/whatever/cancel")
    assert response.status_code == 401


def test_confirm_executes_once_then_404s_on_replay(admin_client, tmp_db, monkeypatch):
    action_id, executed = _propose_schedule_recording_action(admin_client, monkeypatch)

    first = admin_client.post(f"/api/ai/actions/{action_id}/confirm")
    assert first.status_code == 200
    assert first.json() == {"result": {"status": "scheduled"}}
    assert executed["called"] is True

    second = admin_client.post(f"/api/ai/actions/{action_id}/confirm")
    assert second.status_code == 404


def test_confirm_unknown_action_404s(admin_client, tmp_db):
    _save_ai_settings(enable_recording_tools=True)
    response = admin_client.post("/api/ai/actions/does-not-exist/confirm")
    assert response.status_code == 404


def test_cancel_clears_pending_action_so_confirm_404s(admin_client, tmp_db, monkeypatch):
    action_id, executed = _propose_schedule_recording_action(admin_client, monkeypatch)

    cancel_response = admin_client.post(f"/api/ai/actions/{action_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json() == {"ok": True}

    confirm_response = admin_client.post(f"/api/ai/actions/{action_id}/confirm")
    assert confirm_response.status_code == 404
    assert executed["called"] is False


def test_confirm_rechecks_permission_and_never_executes_when_revoked(admin_client, tmp_db, monkeypatch):
    action_id, executed = _propose_schedule_recording_action(admin_client, monkeypatch, enable_recording_tools=True)

    # revoke the permission between propose and confirm
    _save_ai_settings(enable_recording_tools=False)

    response = admin_client.post(f"/api/ai/actions/{action_id}/confirm")

    assert response.status_code == 403
    assert executed["called"] is False

    # the action was consumed on the rejected attempt, so re-enabling can't replay it
    _save_ai_settings(enable_recording_tools=True)
    replay = admin_client.post(f"/api/ai/actions/{action_id}/confirm")
    assert replay.status_code == 404
    assert executed["called"] is False


def test_chat_accepts_null_optional_fields(admin_client, tmp_db, monkeypatch):
    """Clients like Android / kotlinx.serialization may serialize null for
    optional fields (tool_calls: null, tool_call_id: null, name: null, context: null).
    These should not trigger a 422 Unprocessable Entity."""
    _save_ai_settings()
    fake = _ScriptedClient(
        turns=[
            [
                StreamEvent(type="token", text="Hello from server"),
                StreamEvent(type="message_end"),
            ]
        ]
    )
    monkeypatch.setattr(ai_api, "get_ai_client", lambda *a, **kw: fake)

    payload = {
        "messages": [
            {
                "role": "user",
                "content": "hello",
                "tool_calls": None,
                "tool_call_id": None,
                "name": None,
            }
        ],
        "context": None,
    }
    response = admin_client.post("/api/ai/chat", json=payload)
    assert response.status_code == 200
    events = _parse_sse(response.text)
    assert any(e.get("type") == "token" and e.get("text") == "Hello from server" for e in events)

