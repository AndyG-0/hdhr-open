from __future__ import annotations

import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dvr as dvr_api
from app.auth import get_current_user
from app.storage import db


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(dvr_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role": "member"}
    return TestClient(app)


def test_get_dvr_info_builtin_fallback(client, tmp_db):
    response = client.get("/api/dvr/info")
    assert response.status_code == 200
    body = response.json()
    assert body["friendly_name"] == "HDHomeRun Open Built-in DVR"
    assert body["version"] == "1.0"
    assert body["is_builtin"] is True


def test_list_recordings_builtin(client, tmp_db):
    now = time.time()
    db.create_recording(
        {
            "id": "rec_test_1",
            "title": "Jeopardy!",
            "episode_title": "Game 1",
            "season_number": 40,
            "episode_number": 1,
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 1800,
            "file_path": "/tmp/rec_test_1.ts",
            "duration_seconds": 1800.0,
            "status": "completed",
            "synopsis": "Night 1 of Tournament.",
            "original_air_date": "2026-08-18",
            "category": "Game Show",
            "image_url": "http://example.com/j.jpg",
            "has_captions": 1,
            "video_codec": "h264",
            "video_width": 1920,
            "video_height": 1080,
            "audio_codec": "ac3",
            "audio_channels": 6,
            "file_size_bytes": 1048576,
        }
    )

    response = client.get("/api/dvr/recordings")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    rec = body[0]
    assert rec["recording_id"] == "rec_test_1"
    assert rec["title"] == "Jeopardy!"
    assert rec["episode_title"] == "Game 1"
    assert rec["episode_number"] == "40.1"
    assert rec["synopsis"] == "Night 1 of Tournament."
    assert rec["channel_number"] == "4.1"
    assert rec["is_dvr_file"] is True
    assert rec["has_captions"] is True
    assert rec["video_codec"] == "h264"
    assert rec["video_width"] == 1920
    assert rec["video_height"] == 1080
    assert rec["audio_codec"] == "ac3"
    assert rec["audio_channels"] == 6
    assert rec["file_size_bytes"] == 1048576
    assert rec["original_air_date"] == "2026-08-18"
    assert rec["category"] == "Game Show"


def test_get_recording_poster_fallback_and_generation(client, tmp_db, tmp_path, monkeypatch):
    dummy_ts = tmp_path / "test_rec.ts"
    dummy_ts.write_bytes(b"x" * 1000)

    dummy_jpg = tmp_path / "rec_poster.poster.jpg"
    dummy_jpg.write_bytes(b"JPEGDATA")

    from app.dvr import media_cache
    monkeypatch.setattr(media_cache, "generate_poster", AsyncMock(return_value=dummy_jpg))

    db.create_recording(
        {
            "id": "rec_poster",
            "title": "Movie Night",
            "channel_id": "5.1",
            "channel_name_snapshot": "KTLA",
            "start_ts": time.time() - 3600,
            "end_ts": time.time() - 1800,
            "file_path": str(dummy_ts),
            "status": "completed",
            "image_url": None,
        }
    )

    # Should fall back to poster endpoint URL when image_url is None
    rec_list = client.get("/api/dvr/recordings").json()
    assert rec_list[0]["image_url"] == "/api/dvr/recordings/rec_poster/poster.jpg"

    # Request the poster
    resp = client.get("/api/dvr/recordings/rec_poster/poster.jpg")
    assert resp.status_code == 200
    assert resp.content == b"JPEGDATA"


def test_create_and_delete_recording_rule_builtin(client, tmp_db, monkeypatch):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()
    airing_start = int(now + 3600)

    # Seed guide program
    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "hdhomerun_cloud",
                "external_program_id": "EP_JEOPARDY",
                "title": "Jeopardy!",
                "episode_title": "Episode 100",
                "season_number": 40,
                "episode_number": 100,
                "synopsis": "Trivia.",
                "start_ts": float(airing_start),
                "end_ts": float(airing_start + 1800),
                "original_air_date": "2026-08-18",
                "image_url": None,
                "is_new": 1,
                "category": None,
            }
        ]
    )

    # POST create series rule
    payload = {
        "series_id": "EP_JEOPARDY",
        "channel": "4.1",
        "recent_only": True,
        "start_padding": 60,
        "end_padding": 120,
        "max_episodes_to_keep": 3,
    }
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    rules = response.json()
    assert len(rules) == 1
    rule = rules[0]
    assert rule["Title"] == "Jeopardy!"
    assert rule["SeriesID"] == "EP_JEOPARDY"
    assert rule["ChannelOnly"] == "4.1"
    assert rule["StartPadding"] == 60
    assert rule["EndPadding"] == 120
    assert rule["RecentOnly"] == 1
    assert rule["MaxEpisodesToKeep"] == 3

    rule_id = rule["RecordingRuleID"]

    # GET recording-rules
    get_res = client.get("/api/dvr/recording-rules")
    assert get_res.status_code == 200
    assert len(get_res.json()) == 1

    # DELETE recording rule
    del_res = client.delete(f"/api/dvr/recording-rules/{rule_id}")
    assert del_res.status_code == 200
    assert len(del_res.json()) == 0
    assert db.get_recording_rule(rule_id) is None


def test_create_recording_rule_max_episodes_to_keep_omitted(client, tmp_db):
    payload = {"series_id": "auto", "channel": "4.1"}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    rule = response.json()[0]
    assert rule["MaxEpisodesToKeep"] is None


def test_create_recording_rule_max_episodes_to_keep_rejects_zero(client, tmp_db):
    payload = {"series_id": "auto", "channel": "4.1", "max_episodes_to_keep": 0}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 422


def test_delete_recording_builtin(client, tmp_db, tmp_path, monkeypatch):
    from app.dvr.builtin import retention

    monkeypatch.setattr(retention, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(retention, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path / "cache")

    video_file = tmp_path / "test_del.ts"
    video_file.write_bytes(b"DATA")

    db.create_recording(
        {
            "id": "rec_to_delete",
            "title": "Old Episode",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    del_res = client.delete("/api/dvr/recordings/rec_to_delete")
    assert del_res.status_code == 200
    assert del_res.json() == {"status": "deleted"}
    assert not video_file.exists()
    assert db.get_recording("rec_to_delete") is None


def test_delete_recording_not_found(client, tmp_db):
    res = client.delete("/api/dvr/recordings/non_existent_rec")
    assert res.status_code == 404


def test_delete_recording_rejects_in_progress(client, tmp_db, tmp_path, monkeypatch):
    from app.dvr.builtin import retention
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    monkeypatch.setattr(retention, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(retention, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path / "cache")

    video_file = tmp_path / "rec_live.ts"
    video_file.write_bytes(b"DATA")

    db.create_recording(
        {
            "id": "rec_live",
            "title": "Live Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "recording",
        }
    )

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_live",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 60,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_live"] = active_capture

    try:
        res = client.delete("/api/dvr/recordings/rec_live")
        assert res.status_code == 409
        assert video_file.exists()
        assert db.get_recording("rec_live") is not None
    finally:
        capture_pipeline._active_captures.pop("rec_live", None)


def test_create_recording_rule_respects_dvr_server_priority(client, tmp_db, monkeypatch):
    from app.integrations import hdhomerun_client

    db.save_app_settings({"dvr_server_priority": "hdhomerun,builtin"})
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})

    mock_add = AsyncMock(return_value=[{"RecordingRuleID": "off_1", "SeriesID": "auto", "Provider": "hdhomerun"}])
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    payload = {"series_id": "auto", "channel": "4.1"}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    assert mock_add.called


def test_create_recording_rule_explicit_server_override(client, tmp_db, monkeypatch):
    from app.integrations import hdhomerun_client

    # Default priority is hdhomerun, but request specifies server="builtin"
    db.save_app_settings({"dvr_server_priority": "hdhomerun,builtin"})
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})

    mock_add = AsyncMock(return_value=[])
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    payload = {"series_id": "auto", "channel": "4.1", "server": "builtin"}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    # Official DVR add should NOT have been called
    assert not mock_add.called
    rules = response.json()
    assert len(rules) == 1
    assert rules[0]["provider"] == "builtin"


def test_create_recording_rule_explicit_hdhomerun_unconfigured_fails(client, tmp_db):
    payload = {"series_id": "auto", "channel": "4.1", "server": "hdhomerun"}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 400
    assert "not configured" in response.json()["detail"]


def test_recording_detail_probes_in_progress_recording_once_enough_data(client, tmp_db, tmp_path, monkeypatch):
    """An in-progress recording should surface real video/audio metadata
    (needed for the live audio-track/SAP menu and the playback-info panel)
    once media_probe.probe_in_progress finds enough data on disk, instead of
    the old hardcoded empty stub."""
    from app import media_probe as media_probe_module

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "in_progress.ts"
    video_file.write_bytes(b"MPEG-TS data" * 10000)

    now = time.time()
    db.create_recording(
        {
            "id": "rec_live",
            "title": "Live Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 60,
            "end_ts": now + 600,
            "file_path": str(video_file),
            "status": "recording",
        }
    )

    probe_result = {
        "video": {"codec": "mpeg2video", "width": 1280, "height": 720, "fps": 59.94},
        "audio": [{"index": 0, "codec": "ac3", "channels": 6, "language": "eng"}],
        "has_captions": True,
    }
    mock_probe = AsyncMock(return_value=probe_result)
    monkeypatch.setattr(media_probe_module, "probe_in_progress", mock_probe)

    response = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_live", "start": now - 60},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_in_progress"] is True
    assert body["video"] == probe_result["video"]
    assert body["audio"] == probe_result["audio"]
    assert body["has_captions"] is True
    mock_probe.assert_awaited_once()

    # A second poll while still in-progress reuses the cached result rather
    # than probing again.
    response2 = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_live", "start": now - 60},
    )
    assert response2.status_code == 200
    assert response2.json()["video"] == probe_result["video"]
    mock_probe.assert_awaited_once()


def test_recording_detail_surfaces_transcode_preset_for_completed_recording(client, tmp_db, tmp_path):
    """The playback-info panel needs to know whether the server transcodes
    at all, and if so via which preset, to show "Direct passthrough" vs
    "Transcoding via {preset_label}"."""
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local", "hwaccel": "software"}
    )

    video_file = tmp_path / "done.ts"
    video_file.write_bytes(b"MPEG-TS data")

    db.create_recording(
        {
            "id": "rec_done",
            "title": "Finished Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    response = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_done", "start": 1000.0, "record_end": 2000.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_in_progress"] is False
    assert body["transcode"] == {
        "transcoding": True,
        "preset": "software",
        "preset_label": "Software (libx264)",
        "hardware": False,
    }


def test_recording_detail_surfaces_direct_passthrough_when_transcoding_disabled(client, tmp_db, tmp_path):
    # Even with playback_mode="external" (direct passthrough for
    # /recording-stream), preset/hardware are still resolved: native clients'
    # /recording-stream-hls path always transcodes regardless of this
    # setting, so they need real preset info even when "transcoding" is False.
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local", "playback_mode": "external"}
    )

    video_file = tmp_path / "in_progress.ts"
    video_file.write_bytes(b"MPEG-TS data")

    now = time.time()
    db.create_recording(
        {
            "id": "rec_live_passthrough",
            "title": "Live Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 60,
            "end_ts": now + 600,
            "file_path": str(video_file),
            "status": "recording",
        }
    )

    response = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_live_passthrough", "start": now - 60},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_in_progress"] is True
    assert body["transcode"] == {
        "transcoding": False,
        "preset": "software",
        "preset_label": "Software (libx264)",
        "hardware": False,
    }


def test_recording_captions_serves_live_vtt_for_in_progress_recording(client, tmp_db, tmp_path, monkeypatch):
    from app.dvr import media_cache
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    video_file = tmp_path / "in_progress.ts"
    video_file.write_bytes(b"MPEG-TS data")

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_live",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 60,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_live"] = active_capture

    def fake_ensure_live_captions(recording_id, file_path, is_source_alive, capture_start_ts=None):
        media_cache.live_captions_path(recording_id).write_text("WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi\n")

    monkeypatch.setattr(media_cache, "ensure_live_captions", fake_ensure_live_captions)

    try:
        response = client.get(
            "/api/dvr/recording-captions.vtt",
            params={"url": str(video_file), "recording_id": "rec_live", "record_end": now + 600},
        )
        assert response.status_code == 200
        assert "Hi" in response.text
    finally:
        capture_pipeline._active_captures.pop("rec_live", None)
        media_cache.live_captions_path("rec_live").unlink(missing_ok=True)


def test_recording_captions_404_when_capture_gone(client, tmp_db, tmp_path):
    response = client.get(
        "/api/dvr/recording-captions.vtt",
        params={"url": str(tmp_path / "gone.ts"), "recording_id": "rec_gone", "record_end": time.time() + 600},
    )
    assert response.status_code == 404


def _fake_transcode_process() -> MagicMock:
    proc = MagicMock()
    proc.returncode = None
    proc.terminate = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.read = AsyncMock(side_effect=[b"chunk", b""])
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    return proc


def test_recording_stream_proceeds_immediately_once_capture_has_data(client, tmp_db, tmp_path, monkeypatch):
    """A viewer attaching to a capture that's already been writing for a
    while (the common case) shouldn't be slowed down at all by the new
    pre-flight readiness check - the file is already well past the ready
    threshold, so it should pass on the very first check."""
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "live.ts"
    video_file.write_bytes(b"x" * (dvr_api._LIVE_CAPTURE_READY_MIN_BYTES + 1))

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_ready",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 60,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_ready"] = active_capture

    spawn_mock = AsyncMock(side_effect=lambda *a, **kw: _fake_transcode_process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_mock)

    try:
        response = client.get(
            "/api/dvr/recording-stream",
            params={"url": str(video_file), "recording_id": "rec_ready"},
        )
        assert response.status_code == 200
    finally:
        capture_pipeline._active_captures.pop("rec_ready", None)


@pytest.mark.asyncio
async def test_recording_stream_spawn_failure_502s_stops_pump_and_skips_hwaccel_probe(tmp_db, tmp_path, monkeypatch):
    """Reproduces a tail-follow (live) recording-stream whose downstream
    transcode ffmpeg fails to produce any output: the 502 detail should carry
    the real ffmpeg-stderr-derived reason, the tail-follow pump feeding that
    ffmpeg's stdin must be torn down (stop_pump), and - since this is the
    recording-stream path, not live-channel streaming - the hwaccel
    diagnostic probe must never run (see the 3d scope decision: recording
    failures aren't hardware-preset-enriched).

    Calls the route function directly rather than through TestClient: the
    background tasks under test (drain/terminate/stop_pump, all fired via
    run_in_background) need to be awaited deterministically afterward, which
    only works reliably when they're scheduled on this test's own event
    loop rather than on TestClient's separate portal loop/thread.
    """
    from fastapi import HTTPException

    from app import hwaccel
    from app.api import dvr as dvr_module
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "live_failing.ts"
    video_file.write_bytes(b"x" * (dvr_api._LIVE_CAPTURE_READY_MIN_BYTES + 1))

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_spawn_fail",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 60,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_spawn_fail"] = active_capture

    proc = MagicMock()
    proc.returncode = 1
    proc.terminate = MagicMock()
    proc.wait = AsyncMock(return_value=1)
    proc.stdin = MagicMock()
    proc.stdin.close = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.read = AsyncMock(return_value=b"")
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(side_effect=[b"downstream ffmpeg exploded", b""])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))

    async def fake_pump_tail_follow(file_path, writer, stop_event, is_alive, *, start_offset_bytes=None):
        await stop_event.wait()

    monkeypatch.setattr(dvr_module, "pump_tail_follow", fake_pump_tail_follow)

    background_tasks: list[asyncio.Task] = []

    def tracking_run_in_background(coro):
        task = asyncio.ensure_future(coro)
        background_tasks.append(task)
        return task

    monkeypatch.setattr(dvr_module, "run_in_background", tracking_run_in_background)

    mock_probe = AsyncMock()
    monkeypatch.setattr(hwaccel, "probe_transcode", mock_probe)

    try:
        with pytest.raises(HTTPException) as exc_info:
            await dvr_module.stream_recording(url=str(video_file), recording_id="rec_spawn_fail")

        assert exc_info.value.status_code == 502
        detail = exc_info.value.detail
        assert "Could not start streaming recording" in detail
        assert "downstream ffmpeg exploded" in detail

        assert len(background_tasks) == 3  # drain_stderr_tail, terminate_process, stop_pump
        await asyncio.gather(*background_tasks)

        assert proc.stdin.close.called, "stop_pump should have closed the transcode ffmpeg's stdin"
        mock_probe.assert_not_awaited()
    finally:
        capture_pipeline._active_captures.pop("rec_spawn_fail", None)


def test_recording_stream_502s_without_spawning_ffmpeg_when_capture_stays_empty(client, tmp_db, tmp_path, monkeypatch):
    """Reproduces the real-world race: a viewer requests a stream for a
    recording_id whose capture was just registered (see
    CapturePipeline.start_capture, which adds the ActiveCapture the instant
    the writer ffmpeg is spawned - before it has locked the tuner or written
    a single byte). The pre-flight wait should time out and fail fast with a
    clear cause, and - critically - should never spawn the downstream
    transcode ffmpeg at all, since there's nothing yet for it to read."""
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "just_started.ts"
    video_file.write_bytes(b"")  # writer hasn't flushed anything yet

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_empty",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_empty"] = active_capture

    monkeypatch.setattr(dvr_api, "_LIVE_CAPTURE_READY_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(dvr_api, "_LIVE_CAPTURE_READY_POLL_SECONDS", 0.01)
    spawn_mock = AsyncMock(side_effect=lambda *a, **kw: _fake_transcode_process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_mock)

    try:
        response = client.get(
            "/api/dvr/recording-stream",
            params={"url": str(video_file), "recording_id": "rec_empty"},
        )
        assert response.status_code == 502
        assert "tuner did not produce any data" in response.json()["detail"]
        spawn_mock.assert_not_awaited()
    finally:
        capture_pipeline._active_captures.pop("rec_empty", None)


def test_recording_stream_waits_for_readiness_when_capture_file_not_yet_created(client, tmp_db, tmp_path, monkeypatch):
    """Reproduces the live-TV-from-the-guide regression: start_watch registers
    the ActiveCapture and DB row (see CapturePipeline.start_capture) before
    the writer ffmpeg has even created the file on disk - not merely before
    it's flushed any bytes. _resolve_target_media_url must not treat a
    not-yet-created file on an active capture as a deleted recording; it
    should fall through to the normal readiness wait and time out with the
    usual "tuner did not produce any data" 502, not an immediate 404."""
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "not_created_yet.ts"  # writer hasn't even created this file yet

    now = time.time()
    db.create_recording(
        {
            "id": "rec_not_created",
            "title": "Live Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now,
            "end_ts": now + 600,
            "file_path": str(video_file),
            "status": "recording",
        }
    )
    active_capture = ActiveCapture(
        recording_id="rec_not_created",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_not_created"] = active_capture

    monkeypatch.setattr(dvr_api, "_LIVE_CAPTURE_READY_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(dvr_api, "_LIVE_CAPTURE_READY_POLL_SECONDS", 0.01)
    spawn_mock = AsyncMock(side_effect=lambda *a, **kw: _fake_transcode_process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_mock)

    try:
        response = client.get(
            "/api/dvr/recording-stream",
            params={"url": str(video_file), "recording_id": "rec_not_created"},
        )
        assert response.status_code == 502
        assert "tuner did not produce any data" in response.json()["detail"]
        spawn_mock.assert_not_awaited()
    finally:
        capture_pipeline._active_captures.pop("rec_not_created", None)


def test_recording_stream_404s_when_inactive_recording_file_missing(client, tmp_db, tmp_path):
    """A completed (non-active) recording whose file has been deleted off
    disk should still get the clear 404, not the live-capture pass-through -
    guards the original fix this regression test's siblings were narrowing."""
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "deleted.ts"  # never created

    now = time.time()
    db.create_recording(
        {
            "id": "rec_deleted",
            "title": "Old Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 3000,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    response = client.get(
        "/api/dvr/recording-stream",
        params={"url": str(video_file), "recording_id": "rec_deleted"},
    )
    assert response.status_code == 404
    assert "no longer exists on disk" in response.json()["detail"]


def test_resolve_target_media_url_404s_for_unknown_recording_id_without_official_dvr(tmp_db):
    """A recording_id with no matching builtin-DVR row (deleted, stale client
    cache, or bogus) must not be treated as an official HDHomeRun DVR
    recording id when no official DVR is even configured - that used to fall
    through to hdhomerun_client.resolve_recording_url and build a URL against
    the tuner host on dvr_port's default (50000), producing an opaque 404
    from a device that was never the intended target."""
    from fastapi import HTTPException

    settings = {"tuner_host": "hdhomerun.local"}  # tuner only, no dvr_host
    with pytest.raises(HTTPException) as exc_info:
        dvr_api._resolve_target_media_url(settings, "/recorded/rec_missing", "rec_missing")
    assert exc_info.value.status_code == 404


def test_resolve_target_media_url_still_falls_through_when_official_dvr_configured(tmp_db, monkeypatch):
    """The same 'no local row' case must still resolve normally against the
    official HDHomeRun DVR when one is actually configured - this really is
    an official-DVR recording id, not a builtin one, and this path must not
    regress."""
    settings = {"tuner_host": "hdhomerun.local", "dvr_host": "dvr.local", "dvr_port": 50000}
    mock_resolve = MagicMock(return_value="http://dvr.local:50000/recorded/off_1")
    monkeypatch.setattr(dvr_api.hdhomerun_client, "resolve_recording_url", mock_resolve)

    result = dvr_api._resolve_target_media_url(settings, "/recorded/off_1", "off_1")

    assert result == "http://dvr.local:50000/recorded/off_1"
    mock_resolve.assert_called_once_with(settings, "/recorded/off_1")


def test_resolve_target_media_url_404s_for_builtin_provider_even_with_official_dvr_configured(
    tmp_db, monkeypatch
):
    """A client-tagged builtin recording whose row is missing locally (e.g. a
    stale client cache) must 404 with a clear local error - never fall
    through to the official DVR - even when one is configured. Regression
    test for the reported bug: a builtin recording was silently routed to
    the HDHomeRun DVR server (a 404 from port 50000) because the old
    fallthrough was only gated on whether an official DVR was configured at
    all, not on which server the recording actually belonged to."""
    from fastapi import HTTPException

    settings = {"tuner_host": "hdhomerun.local", "dvr_host": "dvr.local", "dvr_port": 50000}
    mock_resolve = MagicMock(return_value="http://dvr.local:50000/recorded/rec_missing")
    monkeypatch.setattr(dvr_api.hdhomerun_client, "resolve_recording_url", mock_resolve)

    with pytest.raises(HTTPException) as exc_info:
        dvr_api._resolve_target_media_url(
            settings, "/recorded/rec_missing", "rec_missing", provider="builtin"
        )

    assert exc_info.value.status_code == 404
    mock_resolve.assert_not_called()


def test_resolve_target_media_url_falls_through_for_hdhomerun_provider(tmp_db, monkeypatch):
    """A client-tagged official-DVR recording must resolve against the
    official DVR as normal."""
    settings = {"tuner_host": "hdhomerun.local", "dvr_host": "dvr.local", "dvr_port": 50000}
    mock_resolve = MagicMock(return_value="http://dvr.local:50000/recorded/off_1")
    monkeypatch.setattr(dvr_api.hdhomerun_client, "resolve_recording_url", mock_resolve)

    result = dvr_api._resolve_target_media_url(
        settings, "/recorded/off_1", "off_1", provider="hdhomerun"
    )

    assert result == "http://dvr.local:50000/recorded/off_1"
    mock_resolve.assert_called_once_with(settings, "/recorded/off_1")


def _spy_on_build_ffmpeg_args(monkeypatch, captured_kwargs: dict):
    real_build = dvr_api.transcoding.build_ffmpeg_args

    def _spy(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(dvr_api.transcoding, "build_ffmpeg_args", _spy)


def test_recording_stream_hls_uses_vod_packaging_for_completed_recording(client, tmp_db, tmp_path, monkeypatch):
    """A finished recording (no active capture) must be packaged with a real
    VOD playlist covering the whole file - not the live-style rolling window
    - so AVPlayer can scrub past the first ~24s. See transcoding.HLS_FLAGS_VOD."""
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "finished.ts"
    video_file.write_bytes(b"x" * 1024)

    now = time.time()
    db.create_recording(
        {
            "id": "rec_finished",
            "title": "Finished Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 3000,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    captured_kwargs: dict = {}
    _spy_on_build_ffmpeg_args(monkeypatch, captured_kwargs)

    fake_session = MagicMock()
    fake_session.session_id = "sess_vod"
    monkeypatch.setattr(dvr_api.hls_streaming, "create_session", AsyncMock(return_value=fake_session))

    response = client.post(
        "/api/dvr/recording-stream-hls",
        json={"url": str(video_file), "recording_id": "rec_finished"},
    )
    assert response.status_code == 200
    assert captured_kwargs["hls_vod"] is True


def test_recording_stream_hls_uses_live_style_packaging_for_active_capture(client, tmp_db, tmp_path, monkeypatch):
    """An in-progress recording/live watch (an active capture exists) must
    keep the existing rolling live-style HLS window - only a completed
    recording gets VOD packaging (regression guard for Fix 1)."""
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "live.ts"
    video_file.write_bytes(b"x" * (dvr_api._LIVE_CAPTURE_READY_MIN_BYTES + 1))

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_live_hls",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 60,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_live_hls"] = active_capture

    captured_kwargs: dict = {}
    _spy_on_build_ffmpeg_args(monkeypatch, captured_kwargs)

    fake_session = MagicMock()
    fake_session.session_id = "sess_live"

    async def _fake_create_session(*args, **kwargs):
        on_process_spawned = kwargs["on_process_spawned"]
        on_process_spawned(_fake_transcode_process())
        return fake_session

    monkeypatch.setattr(dvr_api.hls_streaming, "create_session", _fake_create_session)
    monkeypatch.setattr(dvr_api, "pump_tail_follow", AsyncMock(return_value=None))

    try:
        response = client.post(
            "/api/dvr/recording-stream-hls",
            json={"url": str(video_file), "recording_id": "rec_live_hls"},
        )
        assert response.status_code == 200
        assert captured_kwargs["hls_vod"] is False
    finally:
        capture_pipeline._active_captures.pop("rec_live_hls", None)


def test_estimate_byte_offset_aligns_to_ts_packet_boundary(tmp_path, monkeypatch):
    """`_estimate_byte_offset`'s raw seconds->bytes arithmetic almost never
    lands on a 188-byte MPEG-TS packet boundary; feeding pump_tail_follow an
    unaligned offset desyncs every subsequent packet it reads and corrupts
    the downstream ffmpeg's parse (regression guard for the 502-on-resume
    bug: 'Invalid frame dimensions 0x0' / 'PES packet size mismatch')."""
    video_file = tmp_path / "cap.ts"
    video_file.write_bytes(b"x" * 10_000)

    fixed_now = 1_700_000_000.0
    monkeypatch.setattr(dvr_api.time, "time", lambda: fixed_now)

    capture = MagicMock()
    capture.file_path = video_file
    capture.start_ts = fixed_now - 10  # elapsed=10s, file_size=10000 -> 1000 B/s

    # target_start_seconds=1.0 -> raw arithmetic offset is 1000, which is NOT
    # a multiple of 188 (1000 / 188 = 5.319...) - this is exactly the case
    # that previously corrupted playback.
    offset = dvr_api._estimate_byte_offset(capture, 1.0)
    assert offset == 940  # (1000 // 188) * 188
    assert offset % dvr_api._TS_PACKET_SIZE == 0
    assert offset <= 1000


def test_recording_stream_hls_aligns_resume_offset_to_ts_packet_boundary(client, tmp_db, tmp_path, monkeypatch):
    """Resuming/scrubbing into a still-recording capture must hand
    pump_tail_follow a 188-byte-aligned start_offset_bytes - an unaligned
    offset is what caused 'PES packet size mismatch' / 'Packet corrupt'
    ffmpeg errors and a 502 on recording resume (regression guard)."""
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "live.ts"
    video_file.write_bytes(b"x" * (dvr_api._LIVE_CAPTURE_READY_MIN_BYTES + 1_000))

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_resume",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 10,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_resume"] = active_capture

    captured_kwargs: dict = {}
    _spy_on_build_ffmpeg_args(monkeypatch, captured_kwargs)

    fake_session = MagicMock()
    fake_session.session_id = "sess_resume"

    async def _fake_create_session(*args, **kwargs):
        on_process_spawned = kwargs["on_process_spawned"]
        on_process_spawned(_fake_transcode_process())
        return fake_session

    monkeypatch.setattr(dvr_api.hls_streaming, "create_session", _fake_create_session)

    pump_kwargs: dict = {}

    async def _fake_pump_tail_follow(*args, **kwargs):
        pump_kwargs.update(kwargs)
        return None

    monkeypatch.setattr(dvr_api, "pump_tail_follow", _fake_pump_tail_follow)

    try:
        response = client.post(
            "/api/dvr/recording-stream-hls",
            json={"url": str(video_file), "recording_id": "rec_resume", "start": 1.0},
        )
        assert response.status_code == 200
        offset = pump_kwargs.get("start_offset_bytes")
        assert offset is not None
        assert offset % dvr_api._TS_PACKET_SIZE == 0
    finally:
        capture_pipeline._active_captures.pop("rec_resume", None)
