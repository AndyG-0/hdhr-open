from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.dvr.builtin import sports_extension
from app.dvr.builtin.capture import ActiveCapture, capture_pipeline
from app.storage import db


def _make_active_capture(
    recording_id: str,
    *,
    end_ts: float,
    title: str = "Dallas Cowboys at Arizona Cardinals",
    episode_title: str | None = None,
    category: str | None = "NFL Football",
    start_ts: float | None = None,
) -> ActiveCapture:
    return ActiveCapture(
        recording_id=recording_id,
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title=title,
        episode_title=episode_title,
        season_number=None,
        episode_number=None,
        start_ts=start_ts if start_ts is not None else end_ts - 3600,
        end_ts=end_ts,
        file_path=Path("/tmp/rec.ts"),
        image_url=None,
        process=None,
        category=category,
    )


@pytest.fixture(autouse=True)
def _clear_extension_state():
    sports_extension._original_end_by_recording.clear()
    yield
    sports_extension._original_end_by_recording.clear()


@pytest.fixture
def active_capture(tmp_db):
    now = time.time()
    capture = _make_active_capture("rec_sports", end_ts=now + 120)
    db.create_recording(
        {
            "id": capture.recording_id,
            "title": capture.title,
            "channel_id": capture.channel_number,
            "channel_name_snapshot": capture.channel_name,
            "start_ts": capture.start_ts,
            "end_ts": capture.end_ts,
            "file_path": str(capture.file_path),
            "status": "recording",
        }
    )
    capture_pipeline._active_captures[capture.recording_id] = capture
    try:
        yield capture
    finally:
        capture_pipeline._active_captures.pop(capture.recording_id, None)


@pytest.mark.asyncio
async def test_noop_when_disabled(active_capture, monkeypatch):
    db.save_app_settings({"sports_extension_enabled": "false"})
    mock_status = AsyncMock(return_value="live")
    monkeypatch.setattr(sports_extension, "get_event_status", mock_status)

    await sports_extension.check_and_extend_sports_recordings()

    assert not mock_status.called
    assert capture_pipeline._active_captures["rec_sports"].end_ts == active_capture.end_ts


@pytest.mark.asyncio
async def test_extends_when_status_is_live(active_capture, monkeypatch):
    db.save_app_settings({"sports_extension_enabled": "true", "sports_extension_max_minutes": "60"})
    monkeypatch.setattr(sports_extension, "get_event_status", AsyncMock(return_value="live"))

    original_end = active_capture.end_ts
    await sports_extension.check_and_extend_sports_recordings()

    updated = capture_pipeline._active_captures["rec_sports"]
    assert updated.end_ts == original_end + sports_extension.EXTENSION_SECONDS
    assert db.get_recording("rec_sports")["end_ts"] == updated.end_ts


@pytest.mark.asyncio
async def test_extends_when_status_is_ambiguous(active_capture, monkeypatch):
    """Fail-safe: an unconfirmed status is treated as 'still in progress'."""
    db.save_app_settings({"sports_extension_enabled": "true", "sports_extension_max_minutes": "60"})
    monkeypatch.setattr(sports_extension, "get_event_status", AsyncMock(return_value=None))

    original_end = active_capture.end_ts
    await sports_extension.check_and_extend_sports_recordings()

    assert capture_pipeline._active_captures["rec_sports"].end_ts == original_end + sports_extension.EXTENSION_SECONDS


@pytest.mark.asyncio
async def test_no_extension_when_finished(active_capture, monkeypatch):
    db.save_app_settings({"sports_extension_enabled": "true", "sports_extension_max_minutes": "60"})
    mock_status = AsyncMock(return_value="finished")
    monkeypatch.setattr(sports_extension, "get_event_status", mock_status)

    original_end = active_capture.end_ts
    await sports_extension.check_and_extend_sports_recordings()

    assert mock_status.called
    assert capture_pipeline._active_captures["rec_sports"].end_ts == original_end


@pytest.mark.asyncio
async def test_non_sports_recording_skipped(tmp_db, monkeypatch):
    now = time.time()
    capture = _make_active_capture("rec_show", end_ts=now + 120, title="Local Evening News", category="News")
    capture_pipeline._active_captures[capture.recording_id] = capture
    db.save_app_settings({"sports_extension_enabled": "true"})
    mock_status = AsyncMock(return_value="live")
    monkeypatch.setattr(sports_extension, "get_event_status", mock_status)

    try:
        await sports_extension.check_and_extend_sports_recordings()
    finally:
        capture_pipeline._active_captures.pop(capture.recording_id, None)

    assert not mock_status.called


@pytest.mark.asyncio
async def test_extension_capped_at_max_minutes(active_capture, monkeypatch):
    db.save_app_settings({"sports_extension_enabled": "true", "sports_extension_max_minutes": "10"})
    monkeypatch.setattr(sports_extension, "get_event_status", AsyncMock(return_value="live"))

    original_end = active_capture.end_ts
    cap_end = original_end + 10 * 60

    # First tick extends toward the cap.
    await sports_extension.check_and_extend_sports_recordings()
    updated = capture_pipeline._active_captures["rec_sports"]
    assert updated.end_ts == min(original_end + sports_extension.EXTENSION_SECONDS, cap_end)

    # Repeated ticks never push it past the cap.
    for _ in range(5):
        await sports_extension.check_and_extend_sports_recordings()
    assert capture_pipeline._active_captures["rec_sports"].end_ts <= cap_end


@pytest.mark.asyncio
async def test_outside_lookahead_window_skipped(tmp_db, monkeypatch):
    now = time.time()
    capture = _make_active_capture("rec_far_out", end_ts=now + sports_extension.LOOKAHEAD_SECONDS + 3600)
    capture_pipeline._active_captures[capture.recording_id] = capture
    db.save_app_settings({"sports_extension_enabled": "true"})
    mock_status = AsyncMock(return_value="live")
    monkeypatch.setattr(sports_extension, "get_event_status", mock_status)

    try:
        await sports_extension.check_and_extend_sports_recordings()
    finally:
        capture_pipeline._active_captures.pop(capture.recording_id, None)

    assert not mock_status.called
