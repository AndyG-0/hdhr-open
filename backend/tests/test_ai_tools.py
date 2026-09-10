from __future__ import annotations

import time
import uuid

import pytest

from app.ai.tools import guide as ai_guide
from app.ai.tools import registry
from app.storage import db

ENABLED = {"enable_recording_tools": True}
DISABLED = {"enable_recording_tools": False}


def _seed_channel(number: str = "5.1", name: str = "WABC") -> str:
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, number, name, True)
    return channel_id


def _seed_program(
    channel_id: str, *, title: str, start_ts: float, end_ts: float, synopsis: str | None = None, provider: str = "xmltv"
) -> None:
    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": provider,
                "external_program_id": None,
                "title": title,
                "episode_title": None,
                "season_number": None,
                "episode_number": None,
                "synopsis": synopsis,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "original_air_date": None,
                "image_url": None,
                "is_new": 0,
                "category": None,
                "audio": None,
                "has_subtitles": 1,
            }
        ]
    )


# --- guide tools ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_guide_matches_title_case_insensitively(tmp_db):
    channel_id = _seed_channel()
    now = time.time()
    _seed_program(channel_id, title="The Office", start_ts=now + 3600, end_ts=now + 5400)
    _seed_program(channel_id, title="Unrelated Show", start_ts=now + 5400, end_ts=now + 7200)

    result = await ai_guide.search_guide(query="office")

    assert result["total_matches"] == 1
    assert result["results"][0]["title"] == "The Office"


@pytest.mark.asyncio
async def test_search_guide_matches_synopsis(tmp_db):
    channel_id = _seed_channel()
    now = time.time()
    _seed_program(
        channel_id, title="Some Show", start_ts=now + 3600, end_ts=now + 5400, synopsis="A documentary about sharks"
    )

    result = await ai_guide.search_guide(query="sharks")

    assert result["total_matches"] == 1


@pytest.mark.asyncio
async def test_search_guide_matches_compound_query_via_token_fallback(tmp_db):
    channel_id = _seed_channel()
    now = time.time()
    _seed_program(channel_id, title="Alabama at Georgia", start_ts=now + 3600, end_ts=now + 7200)
    _seed_program(channel_id, title="Ohio State at Michigan", start_ts=now + 7200, end_ts=now + 10800)
    _seed_program(channel_id, title="Unrelated Show", start_ts=now + 10800, end_ts=now + 14400)

    # A plausible re-derived compound query combining both matchups — never a
    # substring of either title, so this only matches via the token fallback.
    result = await ai_guide.search_guide(query="Alabama vs Georgia and Ohio State vs Michigan")

    titles = {r["title"] for r in result["results"]}
    assert titles == {"Alabama at Georgia", "Ohio State at Michigan"}


@pytest.mark.asyncio
async def test_search_guide_short_token_does_not_cause_false_positive_match(tmp_db):
    channel_id = _seed_channel()
    now = time.time()
    _seed_program(channel_id, title="Cat Show", start_ts=now + 3600, end_ts=now + 7200)

    # Splits into short 1-char tokens ("a", "b") that must not spuriously
    # match "Cat Show" (which contains "a").
    result = await ai_guide.search_guide(query="a and b")

    assert result["total_matches"] == 0


@pytest.mark.asyncio
async def test_search_guide_single_word_query_unaffected_by_fallback(tmp_db):
    channel_id = _seed_channel()
    now = time.time()
    _seed_program(channel_id, title="The Office", start_ts=now + 3600, end_ts=now + 5400)
    _seed_program(channel_id, title="Unrelated Show", start_ts=now + 5400, end_ts=now + 7200)

    result = await ai_guide.search_guide(query="office")

    assert result["total_matches"] == 1
    assert result["results"][0]["title"] == "The Office"


@pytest.mark.asyncio
async def test_get_now_playing_returns_current_and_next(tmp_db):
    channel_id = _seed_channel()
    now = time.time()
    _seed_program(channel_id, title="Now Airing", start_ts=now - 300, end_ts=now + 300)
    _seed_program(channel_id, title="Up Next", start_ts=now + 300, end_ts=now + 1800)

    result = await ai_guide.get_now_playing()

    assert len(result["channels"]) == 1
    channel_result = result["channels"][0]
    assert channel_result["now"]["title"] == "Now Airing"
    assert channel_result["next"]["title"] == "Up Next"


@pytest.mark.asyncio
async def test_get_now_playing_unknown_channel_returns_error(tmp_db):
    result = await ai_guide.get_now_playing(channel_number="99.9")
    assert "error" in result


@pytest.mark.asyncio
async def test_get_program_details_finds_matching_airing(tmp_db):
    channel_id = _seed_channel(number="7.1")
    now = time.time()
    _seed_program(channel_id, title="Detailed Show", start_ts=now + 1000, end_ts=now + 2000)

    result = await ai_guide.get_program_details(channel_number="7.1", start=now + 1000)

    assert result["title"] == "Detailed Show"


@pytest.mark.asyncio
async def test_get_program_details_no_match_returns_error(tmp_db):
    _seed_channel(number="7.1")
    result = await ai_guide.get_program_details(channel_number="7.1", start=time.time() + 999999)
    assert "error" in result


@pytest.mark.asyncio
async def test_get_channel_lineup_never_raises_when_tuner_unconfigured(tmp_db):
    _seed_channel(number="2.1", name="Two")

    result = await ai_guide.get_channel_lineup()

    assert result["tuner_count"] == 0
    assert result["tuners_available"] == 0
    assert any(c["channel_number"] == "2.1" for c in result["channels"])


# --- recording tools: registry gating -------------------------------------------


def test_list_tool_specs_excludes_recording_tools_when_disabled(tmp_db):
    specs = registry.list_tool_specs(ai_settings=DISABLED)
    names = {s.name for s in specs}
    assert "search_guide" in names
    assert "schedule_recording" not in names
    assert "list_recordings" not in names


def test_list_tool_specs_includes_recording_tools_when_enabled(tmp_db):
    specs = registry.list_tool_specs(ai_settings=ENABLED)
    names = {s.name for s in specs}
    assert "schedule_recording" in names
    assert "cancel_recording_rule" in names


@pytest.mark.asyncio
async def test_dispatch_blocks_disabled_recording_tool(tmp_db):
    result = await registry.dispatch("schedule_recording", {"channel": "5.1"}, ai_settings=DISABLED)

    assert result.kind == "error"
    assert db.list_recording_rules("builtin") == []


# --- recording tools: preview never mutates -------------------------------------


@pytest.mark.asyncio
async def test_schedule_recording_dispatch_only_calls_preview(tmp_db, monkeypatch):
    called = {"execute": False}

    async def spy_execute(**kwargs):
        called["execute"] = True
        return {}

    monkeypatch.setattr(registry.TOOL_REGISTRY["schedule_recording"], "execute", spy_execute)

    result = await registry.dispatch(
        "schedule_recording", {"channel": "5.1", "series_id": "auto"}, ai_settings=ENABLED
    )

    assert result.kind == "action_preview"
    assert result.action_id is not None
    assert called["execute"] is False
    assert db.list_recording_rules("builtin") == []


@pytest.mark.asyncio
async def test_cancel_recording_rule_preview_does_not_delete(tmp_db):
    rule_id = f"rule_{uuid.uuid4().hex[:8]}"
    db.create_recording_rule(
        {"id": rule_id, "provider": "builtin", "type": "series", "title": "Some Show", "series_match_key": "Some Show"}
    )

    result = await registry.dispatch("cancel_recording_rule", {"rule_id": rule_id}, ai_settings=ENABLED)

    assert result.kind == "action_preview"
    assert result.preview["title"] == "Some Show"
    assert db.get_recording_rule(rule_id) is not None


@pytest.mark.asyncio
async def test_delete_recording_preview_does_not_delete(tmp_db):
    channel_id = _seed_channel()
    recording_id = uuid.uuid4().hex
    db.create_recording(
        {
            "id": recording_id,
            "title": "Some Recording",
            "channel_id": channel_id,
            "channel_name_snapshot": "WABC",
            "start_ts": time.time() - 3600,
            "file_path": "/tmp/does-not-exist-hdhr-open-test.ts",
            "status": "completed",
        }
    )

    result = await registry.dispatch("delete_recording", {"recording_id": recording_id}, ai_settings=ENABLED)

    assert result.kind == "action_preview"
    assert db.get_recording(recording_id) is not None


# --- confirm/cancel execution: consume-once + re-checked permission ------------


@pytest.mark.asyncio
async def test_execute_pending_action_creates_rule_then_consumes_entry(tmp_db):
    dispatch_result = await registry.dispatch(
        "schedule_recording", {"channel": "5.1", "series_id": "auto", "title": "Explicit Title"}, ai_settings=ENABLED
    )
    action_id = dispatch_result.action_id

    first = await registry.execute_pending_action(action_id, ai_settings=ENABLED)
    assert first.kind == "result"
    assert db.list_recording_rules("builtin")[0]["title"] == "Explicit Title"

    second = await registry.execute_pending_action(action_id, ai_settings=ENABLED)
    assert second.kind == "error"
    assert len(db.list_recording_rules("builtin")) == 1


@pytest.mark.asyncio
async def test_execute_pending_action_rechecks_permission_at_confirm_time(tmp_db):
    dispatch_result = await registry.dispatch(
        "schedule_recording", {"channel": "5.1", "series_id": "auto"}, ai_settings=ENABLED
    )
    action_id = dispatch_result.action_id

    result = await registry.execute_pending_action(action_id, ai_settings=DISABLED)

    assert result.kind == "error"
    assert db.list_recording_rules("builtin") == []
    # the pending action was consumed even though it was rejected, so a
    # later re-enable can't replay it either
    replay = await registry.execute_pending_action(action_id, ai_settings=ENABLED)
    assert replay.kind == "error"


@pytest.mark.asyncio
async def test_cancel_pending_action_prevents_execution(tmp_db):
    dispatch_result = await registry.dispatch(
        "schedule_recording", {"channel": "5.1", "series_id": "auto"}, ai_settings=ENABLED
    )
    action_id = dispatch_result.action_id

    registry.clear_pending_action(action_id)

    result = await registry.execute_pending_action(action_id, ai_settings=ENABLED)
    assert result.kind == "error"
    assert db.list_recording_rules("builtin") == []
