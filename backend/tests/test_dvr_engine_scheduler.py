from __future__ import annotations

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.dvr.builtin import engine as dvr_engine
from app.dvr.builtin import watch
from app.dvr.builtin.capture import capture_pipeline
from app.dvr.builtin.engine import DVREngine
from app.dvr.builtin.tuner_allocator import tuner_allocator
from app.integrations import hdhomerun_client
from app.storage import db


@pytest.mark.asyncio
async def test_recover_on_startup(tmp_db, tmp_path):
    video_file = tmp_path / "dangling.ts"
    video_file.write_bytes(b"DATA" * 3000)

    db.create_recording(
        {
            "id": "rec_dangling",
            "title": "Crashed Recording",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "recording",
        }
    )

    with db._connect() as conn:
        conn.execute(
            "INSERT INTO scheduled_recordings (id, channel_id, title, start_ts, end_ts, status) "
            "VALUES ('sched_dangling', '4.1', 'Crashed Recording', 1000.0, 2000.0, 'in_progress')"
        )

    engine = DVREngine()
    await engine.recover_on_startup()

    rec = db.get_recording("rec_dangling")
    assert rec is not None
    assert rec["status"] == "completed"

    with db._connect() as conn:
        row = conn.execute("SELECT status FROM scheduled_recordings WHERE id = 'sched_dangling'").fetchone()
        assert row[0] == "interrupted"


@pytest.mark.asyncio
async def test_dvr_engine_tick_starts_scheduled_recording(tmp_db, monkeypatch):
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local", "tuner_port": 80}
    )

    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)

    now = time.time()
    db.upsert_scheduled_recording(
        {
            "id": "sched_now",
            "channel_id": channel_id,
            "title": "Breaking News",
            "start_ts": now - 10,
            "end_ts": now + 600,
            "status": "scheduled",
        }
    )

    from app.dvr.builtin.capture import capture_pipeline
    from app.dvr.builtin.tuner_allocator import tuner_allocator

    monkeypatch.setattr(tuner_allocator, "acquire_tuner", AsyncMock(return_value=True))
    mock_capture = MagicMock(recording_id="rec_new", end_ts=now + 600)
    monkeypatch.setattr(capture_pipeline, "start_capture", AsyncMock(return_value=mock_capture))

    engine = DVREngine()
    await engine.tick()

    capture_pipeline.start_capture.assert_called_once()


@pytest.mark.asyncio
async def test_scheduled_recording_attaches_to_existing_live_watch_capture(tmp_db, tmp_path, monkeypatch):
    """A scheduled recording whose start time arrives on a channel someone is
    already live-watching must attach to that existing capture instead of
    contending for a second tuner."""
    settings = {"tuner_host": "hdhomerun.local", "tuner_port": 80}
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", settings)

    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)

    def _mock_process() -> MagicMock:
        proc = MagicMock()
        proc.returncode = None
        proc.terminate = MagicMock()
        proc.wait = AsyncMock(return_value=0)
        proc.stderr = MagicMock()
        proc.stderr.read = AsyncMock(return_value=b"")
        return proc

    monkeypatch.setattr(capture_pipeline, "_ensure_recordings_dir", lambda: tmp_path)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=lambda *a, **kw: _mock_process()))
    monkeypatch.setattr(hdhomerun_client, "fetch_discover", AsyncMock(return_value={"TunerCount": 1}))
    monkeypatch.setattr(
        hdhomerun_client, "fetch_tuner_status", AsyncMock(return_value=[{"in_use": False}])
    )

    result = await watch.start_watch("4.1", settings)
    assert result is not None
    recording_id = result["recording_id"]
    assert len(capture_pipeline._active_captures) == 1

    now = time.time()
    db.upsert_scheduled_recording(
        {
            "id": "sched_attach",
            "channel_id": channel_id,
            "title": "Breaking News",
            "start_ts": now - 10,
            "end_ts": now + 600,
            "status": "scheduled",
        }
    )

    engine = DVREngine()
    await engine.tick()

    # Attached to the existing capture rather than starting a second one -
    # only one tuner/capture is in use for the channel.
    assert len(capture_pipeline._active_captures) == 1
    assert tuner_allocator._channel_owners.get("4.1") == {result["session_id"], recording_id}

    with db._connect() as conn:
        row = conn.execute(
            "SELECT status, recording_id FROM scheduled_recordings WHERE id = 'sched_attach'"
        ).fetchone()
    assert row[0] == "in_progress"
    assert row[1] == recording_id

    rec = db.get_recording(recording_id)
    assert rec["is_temporary"] == 0
    assert rec["title"] == "Breaking News"

    # Cleanup: release the tuner tokens this test acquired.
    await watch.stop_watch(result["session_id"])
    await tuner_allocator.release_tuner(recording_id)


def test_register_scheduler_jobs():
    scheduler = AsyncIOScheduler()
    dvr_engine.register(scheduler)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert "builtin_dvr_engine_tick" in job_ids
    assert "builtin_dvr_rule_expansion" in job_ids
    assert "builtin_dvr_retention_pass" in job_ids
