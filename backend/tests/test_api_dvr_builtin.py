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


def test_create_recording_rule_respects_dvr_server_priority(client, tmp_db, monkeypatch):
    from app.integrations import hdhomerun_client

    db.save_app_settings({"dvr_server_priority": "hdhomerun,builtin"})
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 59090})

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
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 59090})

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
    assert body["transcode"] == {"transcoding": False, "preset": None, "preset_label": None, "hardware": False}


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
