from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock

import pytest

from app.integrations import hdhomerun_client, hdhomerun_series_watch
from app.storage import db


def _make_watch(
    *,
    series_id: str = "EP_JEOP_999",
    channel: str | None = "4.1",
    new_only: bool = False,
    start_padding: int = 0,
    end_padding: int = 0,
) -> dict:
    rule = {
        "id": f"rule_{uuid.uuid4().hex[:12]}",
        "provider": "hdhomerun_series_watch",
        "type": "series",
        "title": "Jeopardy!",
        "series_match_key": series_id,
        "channel_id": channel,
        "start_padding_seconds": start_padding,
        "end_padding_seconds": end_padding,
        "new_only": int(new_only),
        "priority": 0,
    }
    db.create_recording_rule(rule)
    return rule


def _make_airing(
    *,
    prog_id: str = "prog_jeop",
    channel_id: str = "ch_41",
    series_id: str = "EP_JEOP_999",
    start_ts: float,
    is_new: bool | None = None,
    source_provider: str = "hdhomerun_cloud",
) -> dict:
    airing = {
        "id": prog_id,
        "channel_id": channel_id,
        "source_provider": source_provider,
        "external_program_id": series_id,
        "title": "Jeopardy!",
        "start_ts": start_ts,
        "end_ts": start_ts + 1800,
    }
    if is_new is not None:
        airing["is_new"] = is_new
    db.upsert_guide_programs([airing])
    return airing


@pytest.fixture(autouse=True)
def _channel(tmp_db):
    db.upsert_channel("ch_41", "4.1", "KTVK", True)


def test_find_next_occurrence_picks_earliest_within_window():
    watch = _make_watch()
    now = time.time()
    _make_airing(prog_id="prog_far", start_ts=now + 2 * 86400)
    _make_airing(prog_id="prog_near", start_ts=now + 6 * 3600)

    occurrence = hdhomerun_series_watch._find_next_occurrence(watch)

    assert occurrence is not None
    assert occurrence["id"] == "prog_near"


def test_find_next_occurrence_excludes_too_soon_and_too_far():
    watch = _make_watch()
    now = time.time()
    _make_airing(prog_id="prog_too_soon", start_ts=now + 60)
    _make_airing(prog_id="prog_too_far", start_ts=now + 5 * 86400)

    assert hdhomerun_series_watch._find_next_occurrence(watch) is None


def test_find_next_occurrence_ignores_other_series_and_providers():
    watch = _make_watch()
    now = time.time()
    _make_airing(prog_id="prog_other_series", series_id="EP_OTHER", start_ts=now + 6 * 3600)
    _make_airing(prog_id="prog_other_provider", start_ts=now + 6 * 3600, source_provider="xmltv")

    assert hdhomerun_series_watch._find_next_occurrence(watch) is None


def test_find_next_occurrence_respects_new_only():
    watch = _make_watch(new_only=True)
    now = time.time()
    _make_airing(prog_id="prog_rerun", start_ts=now + 6 * 3600, is_new=False)

    assert hdhomerun_series_watch._find_next_occurrence(watch) is None

    _make_airing(prog_id="prog_new", start_ts=now + 12 * 3600, is_new=True)

    occurrence = hdhomerun_series_watch._find_next_occurrence(watch)
    assert occurrence is not None
    assert occurrence["id"] == "prog_new"


def test_find_next_occurrence_restricts_to_watch_channel():
    watch = _make_watch(channel="7.1")  # not a known channel_number
    now = time.time()
    _make_airing(start_ts=now + 6 * 3600)

    # channel_id "7.1" doesn't match any known channel_number, so the watch
    # falls back to searching all channels rather than matching nothing.
    occurrence = hdhomerun_series_watch._find_next_occurrence(watch)
    assert occurrence is not None


def test_already_scheduled_within_tolerance():
    start_ts = time.time() + 86400
    existing = [{"SeriesID": "EP_JEOP_999", "DateTimeOnly": int(start_ts) + 60}]
    assert hdhomerun_series_watch._already_scheduled(existing, "EP_JEOP_999", start_ts)


def test_already_scheduled_false_for_different_series_or_time():
    start_ts = time.time() + 86400
    existing = [{"SeriesID": "EP_OTHER", "DateTimeOnly": int(start_ts)}]
    assert not hdhomerun_series_watch._already_scheduled(existing, "EP_JEOP_999", start_ts)

    existing = [{"SeriesID": "EP_JEOP_999", "DateTimeOnly": int(start_ts) + 3600}]
    assert not hdhomerun_series_watch._already_scheduled(existing, "EP_JEOP_999", start_ts)


@pytest.mark.asyncio
async def test_sync_series_watches_creates_rule_for_next_occurrence(monkeypatch):
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})
    _make_watch()
    now = time.time()
    _make_airing(start_ts=now + 6 * 3600)

    monkeypatch.setattr(hdhomerun_client, "fetch_dvr_recording_rules", AsyncMock(return_value=[]))
    mock_add = AsyncMock()
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    await hdhomerun_series_watch.sync_series_watches()

    assert mock_add.called
    _settings, rule_data = mock_add.call_args[0]
    assert rule_data["series_id"] == "EP_JEOP_999"
    assert rule_data["channel"] == "4.1"


@pytest.mark.asyncio
async def test_sync_series_watches_skips_when_already_scheduled(monkeypatch):
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})
    _make_watch()
    now = time.time()
    _make_airing(start_ts=now + 6 * 3600)

    existing = [{"SeriesID": "EP_JEOP_999", "DateTimeOnly": int(now + 6 * 3600)}]
    monkeypatch.setattr(hdhomerun_client, "fetch_dvr_recording_rules", AsyncMock(return_value=existing))
    mock_add = AsyncMock()
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    await hdhomerun_series_watch.sync_series_watches()

    assert not mock_add.called


@pytest.mark.asyncio
async def test_sync_series_watches_noop_without_watches(monkeypatch):
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})
    mock_fetch = AsyncMock()
    monkeypatch.setattr(hdhomerun_client, "fetch_dvr_recording_rules", mock_fetch)

    await hdhomerun_series_watch.sync_series_watches()

    assert not mock_fetch.called


@pytest.mark.asyncio
async def test_sync_series_watches_noop_when_dvr_not_configured(monkeypatch):
    _make_watch()
    mock_fetch = AsyncMock()
    monkeypatch.setattr(hdhomerun_client, "fetch_dvr_recording_rules", mock_fetch)

    # No network integration saved at all - is_dvr_configured/is_tuner_configured are both false.
    await hdhomerun_series_watch.sync_series_watches()

    assert not mock_fetch.called


@pytest.mark.asyncio
async def test_sync_series_watches_continues_after_one_failure(monkeypatch):
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})
    _make_watch(series_id="EP_FAIL")
    _make_watch(series_id="EP_OK")
    now = time.time()
    _make_airing(prog_id="prog_fail", series_id="EP_FAIL", start_ts=now + 6 * 3600)
    _make_airing(prog_id="prog_ok", series_id="EP_OK", start_ts=now + 6 * 3600)

    monkeypatch.setattr(hdhomerun_client, "fetch_dvr_recording_rules", AsyncMock(return_value=[]))

    async def fake_add(_settings, rule_data):
        if rule_data["series_id"] == "EP_FAIL":
            raise hdhomerun_client.HDHomeRunError("boom")
        return [{"RecordingRuleID": "rule_ok"}]

    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", AsyncMock(side_effect=fake_add))

    # Should not raise despite one watch's add_recording_rule failing.
    await hdhomerun_series_watch.sync_series_watches()
