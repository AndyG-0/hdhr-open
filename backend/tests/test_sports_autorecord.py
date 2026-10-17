from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dvr.builtin import sports_autorecord
from app.storage import db


def _make_game(
    *,
    event_id: str = "evt_1",
    start_time: float | None = None,
    broadcast_network: str | None = "CBS",
    season_type: int | None = 2,
    matchup_title: str = "Dallas Cowboys at Arizona Cardinals",
) -> dict:
    return {
        "event_id": event_id,
        "start_time": start_time if start_time is not None else time.time() + 7 * 86400,
        "broadcast_network": broadcast_network,
        "season_type": season_type,
        "matchup_title": matchup_title,
    }


@pytest.fixture
def favorite(tmp_db):
    fav = {
        "id": "fav_1",
        "kind": "team",
        "league": "nfl",
        "espn_team_id": "6",
        "team_display_name": "Dallas Cowboys",
        "enabled": True,
    }
    db.create_sports_favorite(fav)
    return fav


@pytest.fixture
def mapped_channel(tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "7.1", "KCBS", True)
    db.save_network_channel_map_entry("CBS", channel_id)
    return channel_id


def _enable_autorecord(**overrides):
    settings = {"sports_autorecord_enabled": "true"}
    settings.update(overrides)
    db.save_app_settings(settings)


def test_register_runs_sync_immediately_on_startup():
    scheduler = MagicMock()

    sports_autorecord.register(scheduler)

    assert scheduler.add_job.called
    _, kwargs = scheduler.add_job.call_args
    assert "next_run_time" in kwargs  # don't wait a full SYNC_INTERVAL_SECONDS after a fresh restart


@pytest.mark.asyncio
async def test_noop_when_disabled(favorite, monkeypatch):
    db.save_app_settings({"sports_autorecord_enabled": "false"})
    mock_schedule = AsyncMock(return_value=[_make_game()])
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", mock_schedule)

    await sports_autorecord.sync_sports_autorecord()

    assert not mock_schedule.called
    assert db.list_tracked_events() == []


@pytest.mark.asyncio
async def test_disabled_favorite_skipped(favorite, monkeypatch):
    db.update_sports_favorite(favorite["id"], enabled=0)
    _enable_autorecord()
    mock_schedule = AsyncMock(return_value=[_make_game()])
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", mock_schedule)

    await sports_autorecord.sync_sports_autorecord()

    assert not mock_schedule.called


@pytest.mark.asyncio
async def test_unmapped_network_creates_tracking_only_row(favorite, monkeypatch):
    _enable_autorecord()
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[_make_game()]))

    await sports_autorecord.sync_sports_autorecord()

    tracked = db.list_tracked_events()
    assert len(tracked) == 1
    assert tracked[0]["recording_rule_id"] is None
    assert tracked[0]["network_name"] == "CBS"
    assert db.list_recording_rules() == []


@pytest.mark.asyncio
async def test_mapped_network_creates_rule_and_tracked_row(favorite, mapped_channel, monkeypatch):
    _enable_autorecord()
    game = _make_game()
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[game]))

    await sports_autorecord.sync_sports_autorecord()

    rules = db.list_recording_rules(provider="builtin")
    assert len(rules) == 1
    rule = rules[0]
    assert rule["type"] == "single"
    assert rule["channel_id"] == "7.1"  # the channel NUMBER, not the mapped UUID
    # Built-in is the default (first-priority) engine, so this isn't a
    # fallback - the UI shouldn't badge it as one.
    assert rule["fallback_reason"] is None

    tracked = db.list_tracked_events()
    assert len(tracked) == 1
    assert tracked[0]["recording_rule_id"] == rule["id"]
    # No guide listing exists yet, so the title falls back and isn't "resolved".
    assert tracked[0]["title_resolved"] == 0
    assert tracked[0]["matchup_title"] == game["matchup_title"]


@pytest.mark.asyncio
async def test_hdhomerun_preferred_still_lands_on_builtin_but_flagged(favorite, mapped_channel, monkeypatch):
    # Sports auto-record always creates on Built-in regardless of priority -
    # when the user actually prefers hdhomerun, that's a genuine deviation
    # and should still be badged as a fallback.
    _enable_autorecord(dvr_server_priority="hdhomerun,builtin")
    game = _make_game()
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[game]))

    await sports_autorecord.sync_sports_autorecord()

    rules = db.list_recording_rules(provider="builtin")
    assert len(rules) == 1
    assert rules[0]["fallback_reason"] == "sports_autorecord"


@pytest.mark.asyncio
async def test_rescheduled_game_recreates_rule(favorite, mapped_channel, monkeypatch):
    _enable_autorecord()
    game = _make_game()
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[game]))
    await sports_autorecord.sync_sports_autorecord()
    original_rule_id = db.list_tracked_events()[0]["recording_rule_id"]

    rescheduled = dict(game, start_time=game["start_time"] + 3600)
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[rescheduled]))
    await sports_autorecord.sync_sports_autorecord()

    assert db.get_recording_rule(original_rule_id) is None
    tracked = db.list_tracked_events()
    assert len(tracked) == 1
    assert tracked[0]["recording_rule_id"] != original_rule_id
    assert tracked[0]["start_ts"] == rescheduled["start_time"]


@pytest.mark.asyncio
async def test_near_air_falls_back_to_matchup_title_contains_match(favorite, mapped_channel, monkeypatch):
    _enable_autorecord()
    game = _make_game(start_time=time.time() + 3600)  # well within the title-resolution cutoff
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[game]))

    await sports_autorecord.sync_sports_autorecord()

    rule = db.list_recording_rules(provider="builtin")[0]
    assert rule["title"] == game["matchup_title"]
    assert rule["title_match_mode"] == "contains"


@pytest.mark.asyncio
async def test_ota_network_auto_resolves_to_single_affiliate_match(favorite, monkeypatch):
    _enable_autorecord()
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "7.1", "KCBS", True, affiliate="CBS")
    game = _make_game()  # broadcast_network="CBS", no manual mapping exists
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[game]))

    await sports_autorecord.sync_sports_autorecord()

    rules = db.list_recording_rules(provider="builtin")
    assert len(rules) == 1
    assert rules[0]["channel_id"] == "7.1"

    network_map = {row["network_name"]: row for row in db.list_network_channel_map()}
    assert network_map["CBS"]["channel_id"] == channel_id
    assert network_map["CBS"]["source"] == "auto"


@pytest.mark.asyncio
async def test_ota_network_with_no_local_affiliate_stays_unresolved(favorite, monkeypatch):
    _enable_autorecord()
    game = _make_game()  # broadcast_network="CBS", no channel has a CBS affiliate
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[game]))

    await sports_autorecord.sync_sports_autorecord()

    assert db.list_recording_rules() == []
    tracked = db.list_tracked_events()
    assert len(tracked) == 1
    assert tracked[0]["network_name"] == "CBS"
    assert tracked[0]["matchup_title"] == game["matchup_title"]
    assert db.list_network_channel_map() == []


@pytest.mark.asyncio
async def test_ota_network_with_ambiguous_affiliate_match_stays_unresolved(favorite, monkeypatch):
    _enable_autorecord()
    db.upsert_channel(uuid.uuid4().hex, "7.1", "KCBS", True, affiliate="CBS")
    db.upsert_channel(uuid.uuid4().hex, "7.2", "KCBS-2", True, affiliate="CBS")
    game = _make_game()
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[game]))

    await sports_autorecord.sync_sports_autorecord()

    assert db.list_recording_rules() == []
    assert db.list_network_channel_map() == []
    tracked = db.list_tracked_events()
    assert len(tracked) == 1
    assert tracked[0]["network_name"] == "CBS"


@pytest.mark.asyncio
async def test_manual_mapping_takes_precedence_over_ota_auto_resolution(favorite, monkeypatch):
    _enable_autorecord()
    auto_channel_id = uuid.uuid4().hex
    db.upsert_channel(auto_channel_id, "7.1", "KCBS", True, affiliate="CBS")
    manual_channel_id = uuid.uuid4().hex
    db.upsert_channel(manual_channel_id, "9.1", "KCBS Alt", True)
    db.save_network_channel_map_entry("CBS", manual_channel_id)
    game = _make_game()
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[game]))

    await sports_autorecord.sync_sports_autorecord()

    rules = db.list_recording_rules(provider="builtin")
    assert len(rules) == 1
    assert rules[0]["channel_id"] == "9.1"
    assert db.list_network_channel_map()[0]["source"] == "manual"


@pytest.mark.asyncio
async def test_cable_network_never_auto_resolves(favorite, monkeypatch):
    _enable_autorecord()
    db.upsert_channel(uuid.uuid4().hex, "7.1", "KCBS", True, affiliate="CBS")
    game = _make_game(broadcast_network="ESPN")
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[game]))

    await sports_autorecord.sync_sports_autorecord()

    assert db.list_recording_rules() == []
    assert db.list_network_channel_map() == []
    tracked = db.list_tracked_events()
    assert tracked[0]["network_name"] == "ESPN"


@pytest.mark.asyncio
async def test_deleting_favorite_leaves_sync_to_clean_up_orphaned_tracking(favorite, mapped_channel, monkeypatch):
    _enable_autorecord()
    game = _make_game()
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[game]))
    await sports_autorecord.sync_sports_autorecord()
    rule_id = db.list_tracked_events()[0]["recording_rule_id"]

    db.delete_recording_rule(rule_id)
    db.delete_sports_favorite(favorite["id"])
    monkeypatch.setattr(sports_autorecord.espn, "get_team_schedule", AsyncMock(return_value=[]))

    await sports_autorecord.sync_sports_autorecord()

    assert db.list_tracked_events() == []
