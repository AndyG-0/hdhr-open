from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import hwaccel
from app.api import dvr_streaming
from app.api import streaming as streaming_api
from app.auth import get_current_user
from app.dvr.builtin import watch
from app.dvr.builtin.capture import ActiveCapture, capture_pipeline
from app.dvr.builtin.tuner_allocator import tuner_allocator
from app.storage import db
from app.subprocess_streaming import FFMPEG_NOT_FOUND_DETAIL


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(streaming_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role": "member"}
    return TestClient(app)


def _configure_tuner(hwaccel_preset: str = "software") -> None:
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local", "hwaccel": hwaccel_preset}
    )


def _fake_ffmpeg_process(*, returncode: int | None, stderr_chunks: list[bytes]) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=returncode)
    proc.stdout = MagicMock()
    proc.stdout.read = AsyncMock(return_value=b"")
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(side_effect=[*stderr_chunks, b""])
    return proc


def test_stream_channel_immediate_exit_returns_502_with_ffmpeg_reason(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    proc = _fake_ffmpeg_process(returncode=1, stderr_chunks=[b"no soup for you"])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))

    response = client.get("/api/streaming/stream/4.1")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Could not start streaming channel 4.1" in detail
    assert "exited with code 1" in detail
    assert "no soup for you" in detail


def test_stream_channel_repeat_request_after_502_fails_fast_without_respawning(client, tmp_db, monkeypatch):
    """The web player re-requests the exact same URL right after a failed
    stream to read the 502 detail its player library discarded (see
    frontend/src/lib/mpegts-player.ts). That only works as intended if the
    repeat request doesn't redo the whole slow ffmpeg-startup dance."""
    _configure_tuner("software")
    proc = _fake_ffmpeg_process(returncode=1, stderr_chunks=[b"no soup for you"])
    spawn_mock = AsyncMock(return_value=proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_mock)

    first = client.get("/api/streaming/stream/4.1")
    assert first.status_code == 502

    second = client.get("/api/streaming/stream/4.1")
    assert second.status_code == 502
    assert second.json()["detail"] == first.json()["detail"]
    spawn_mock.assert_awaited_once()


def test_stream_channel_missing_ffmpeg_binary_returns_unified_503(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError()))

    response = client.get("/api/streaming/stream/4.1")

    assert response.status_code == 503
    assert response.json()["detail"] == FFMPEG_NOT_FOUND_DETAIL


def test_stream_channel_hardware_preset_failure_invokes_probe(client, tmp_db, monkeypatch):
    _configure_tuner("videotoolbox")
    proc = _fake_ffmpeg_process(returncode=1, stderr_chunks=[b"gpu init failed"])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))

    mock_probe = AsyncMock(
        return_value={"ok": False, "command": "ffmpeg -probe", "exit_code": 1, "output": "gpu also broken"}
    )
    monkeypatch.setattr(hwaccel, "probe_transcode", mock_probe)

    response = client.get("/api/streaming/stream/4.1")

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "A test transcode with these same settings also failed" in detail
    mock_probe.assert_awaited_once()


def test_stream_channel_repeat_request_after_hardware_probe_failure_skips_probe(client, tmp_db, monkeypatch):
    """Same fast-fail contract as the software-preset case above, but for the
    hardware-preset path whose first failure pays for a diagnostic re-probe
    (see _probe_after_failure) - the retry must not pay for that twice."""
    _configure_tuner("videotoolbox")
    proc = _fake_ffmpeg_process(returncode=1, stderr_chunks=[b"gpu init failed"])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))

    mock_probe = AsyncMock(
        return_value={"ok": False, "command": "ffmpeg -probe", "exit_code": 1, "output": "gpu also broken"}
    )
    monkeypatch.setattr(hwaccel, "probe_transcode", mock_probe)

    first = client.get("/api/streaming/stream/4.1")
    assert first.status_code == 502
    mock_probe.assert_awaited_once()

    second = client.get("/api/streaming/stream/4.1")
    assert second.status_code == 502
    assert second.json()["detail"] == first.json()["detail"]
    mock_probe.assert_awaited_once()  # still just the one call, not a second one


def test_stream_channel_software_preset_failure_does_not_invoke_probe(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    proc = _fake_ffmpeg_process(returncode=1, stderr_chunks=[b"tuner busy"])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))

    mock_probe = AsyncMock()
    monkeypatch.setattr(hwaccel, "probe_transcode", mock_probe)

    response = client.get("/api/streaming/stream/4.1")

    assert response.status_code == 502
    mock_probe.assert_not_awaited()


class _FakeRawResponse:
    def __init__(self, status_code: int, chunks: list[bytes]) -> None:
        self.status_code = status_code
        self._chunks = chunks
        self.aclose = AsyncMock()

    async def aiter_bytes(self, chunk_size: int):
        for chunk in self._chunks:
            yield chunk


class _FakeRawClient:
    def __init__(self, outcome: _FakeRawResponse | Exception) -> None:
        self._outcome = outcome
        self.aclose = AsyncMock()

    def build_request(self, method: str, url: str):
        return (method, url)

    async def send(self, request, stream: bool = False):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _patch_raw_client(monkeypatch, outcome: _FakeRawResponse | Exception) -> None:
    monkeypatch.setattr(streaming_api.httpx, "AsyncClient", lambda **kwargs: _FakeRawClient(outcome))


def test_stream_channel_direct_bypasses_ffmpeg_and_proxies_raw_bytes(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    _patch_raw_client(monkeypatch, _FakeRawResponse(200, [b"abc", b"def"]))
    exec_mock = AsyncMock(side_effect=AssertionError("ffmpeg should not run for direct=true"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", exec_mock)

    response = client.get("/api/streaming/stream/4.1?direct=true")

    assert response.status_code == 200
    assert response.content == b"abcdef"
    assert response.headers["content-type"] == "video/mp2t"
    exec_mock.assert_not_awaited()


def test_stream_channel_direct_returns_502_when_tuner_rejects(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    _patch_raw_client(monkeypatch, _FakeRawResponse(500, []))

    response = client.get("/api/streaming/stream/4.1?direct=true")

    assert response.status_code == 502
    assert "Tuner rejected" in response.json()["detail"]


def test_stream_channel_direct_returns_502_when_tuner_unreachable(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    _patch_raw_client(monkeypatch, httpx.ConnectError("connection refused"))

    response = client.get("/api/streaming/stream/4.1?direct=true")

    assert response.status_code == 502
    assert "Could not reach tuner" in response.json()["detail"]


# --- POST /hls/{channel_number} (CC-2 full-backend-fix fallback path) -----


@pytest.fixture(autouse=True)
def _reset_capture_singletons():
    """capture_pipeline and tuner_allocator are process-wide singletons (same
    ones the real app uses), so tests must not leak active state between
    each other."""
    capture_pipeline._active_captures.clear()
    capture_pipeline._channel_index.clear()
    tuner_allocator._channel_owners.clear()
    tuner_allocator._token_channel.clear()
    yield
    capture_pipeline._active_captures.clear()
    capture_pipeline._channel_index.clear()
    tuner_allocator._channel_owners.clear()
    tuner_allocator._token_channel.clear()


def _make_active_capture(recording_id: str, channel_number: str, file_path) -> ActiveCapture:
    now = time.time()
    return ActiveCapture(
        recording_id=recording_id,
        scheduled_id=None,
        rule_id=None,
        channel_number=channel_number,
        channel_name="WNBC",
        title="Fallback Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now,
        end_ts=now + 3600,
        file_path=file_path,
        image_url=None,
        process=None,
        is_temporary=True,
    )


def _create_recording_row(recording_id: str, channel_number: str, file_path) -> None:
    now = time.time()
    db.create_recording(
        {
            "id": recording_id,
            "title": "Fallback Show",
            "channel_id": channel_number,
            "channel_name_snapshot": "WNBC",
            "start_ts": now,
            "end_ts": now + 3600,
            "file_path": str(file_path),
            "status": "recording",
            "is_temporary": True,
        }
    )


def test_stream_channel_hls_backs_stream_with_real_capture_and_returns_metadata(client, tmp_db, tmp_path, monkeypatch):
    """The full-backend-fix behavior: a successful fallback capture backs the
    HLS session (live-style tail-follow, not the bare raw-URL pipe), and the
    response carries real recording metadata (title, has_captions, etc.) the
    same shape /api/watch/{channel}/start returns - this is what the client
    needs to call loadRecordingMetadata() on this path too."""
    _configure_tuner("software")
    video_file = tmp_path / "live.ts"
    video_file.write_bytes(b"x" * 64_000)

    active_capture = _make_active_capture("rec_fallback", "4.1", video_file)
    capture_pipeline._active_captures["rec_fallback"] = active_capture
    _create_recording_row("rec_fallback", "4.1", video_file)

    monkeypatch.setattr(watch, "start_fallback_capture", AsyncMock(return_value="rec_fallback"))
    release_mock = AsyncMock()
    monkeypatch.setattr(watch, "release_fallback_capture", release_mock)

    fake_session = MagicMock()
    fake_session.session_id = "sess_fallback"

    async def _fake_create_session(*args, **kwargs):
        on_process_spawned = kwargs["on_process_spawned"]
        proc = MagicMock()
        proc.stdin = MagicMock()
        on_process_spawned(proc)
        return fake_session

    monkeypatch.setattr(streaming_api.hls_streaming, "create_session", _fake_create_session)
    monkeypatch.setattr(streaming_api, "pump_tail_follow", AsyncMock(return_value=None))

    response = client.post("/api/streaming/hls/4.1")

    assert response.status_code == 200
    body = response.json()
    assert body["recording_id"] == "rec_fallback"
    assert body["title"] == "Fallback Show"
    assert body["session_id"] == "sess_fallback"
    assert body["playlist_url"] == "/api/hls/sess_fallback/playlist.m3u8"


def test_stream_channel_hls_falls_back_to_raw_url_when_no_capture(client, tmp_db, monkeypatch):
    """When start_fallback_capture can't get even an unmanaged capture going
    (e.g. ffmpeg unspawnable), this must still degrade to today's bare
    raw-URL pipe rather than failing the whole request."""
    _configure_tuner("software")
    monkeypatch.setattr(watch, "start_fallback_capture", AsyncMock(return_value=None))

    fake_session = MagicMock()
    fake_session.session_id = "sess_raw"
    create_session_mock = AsyncMock(return_value=fake_session)
    monkeypatch.setattr(streaming_api.hls_streaming, "create_session", create_session_mock)

    response = client.post("/api/streaming/hls/4.1")

    assert response.status_code == 200
    body = response.json()
    assert "recording_id" not in body
    assert body["session_id"] == "sess_raw"
    # Clients decode this response as recording metadata regardless of path,
    # so `title` must still be present even with no capture behind it.
    assert body["title"]
    assert create_session_mock.await_args.kwargs["stdin_pipe"] is False


def test_stream_channel_hls_releases_fallback_capture_when_create_session_fails(client, tmp_db, tmp_path, monkeypatch):
    _configure_tuner("software")
    video_file = tmp_path / "live.ts"
    video_file.write_bytes(b"x" * 64_000)

    active_capture = _make_active_capture("rec_fail", "4.1", video_file)
    capture_pipeline._active_captures["rec_fail"] = active_capture
    _create_recording_row("rec_fail", "4.1", video_file)

    monkeypatch.setattr(watch, "start_fallback_capture", AsyncMock(return_value="rec_fail"))
    release_mock = AsyncMock()
    monkeypatch.setattr(watch, "release_fallback_capture", release_mock)
    monkeypatch.setattr(
        streaming_api.hls_streaming,
        "create_session",
        AsyncMock(side_effect=streaming_api.hls_streaming.HLSStartupError("boom")),
    )

    response = client.post("/api/streaming/hls/4.1")

    assert response.status_code == 502
    release_mock.assert_awaited_once()
    assert release_mock.await_args.args[0] == "rec_fail"
    assert release_mock.await_args.args[1] == "4.1"


def test_stream_channel_hls_releases_fallback_capture_when_data_never_arrives(client, tmp_db, tmp_path, monkeypatch):
    """A fallback capture that never produces data (tuner still locking, or
    dead on arrival) must release its viewer token and fall through to the
    raw-URL path instead of hanging or leaking the capture's reservation."""
    _configure_tuner("software")
    video_file = tmp_path / "live.ts"
    # Empty file => _wait_for_live_capture_data never sees enough bytes.
    video_file.write_bytes(b"")

    active_capture = _make_active_capture("rec_stall", "4.1", video_file)
    capture_pipeline._active_captures["rec_stall"] = active_capture
    _create_recording_row("rec_stall", "4.1", video_file)

    monkeypatch.setattr(watch, "start_fallback_capture", AsyncMock(return_value="rec_stall"))
    release_mock = AsyncMock()
    monkeypatch.setattr(watch, "release_fallback_capture", release_mock)
    monkeypatch.setattr(streaming_api, "_LIVE_CAPTURE_READY_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(dvr_streaming, "_LIVE_CAPTURE_READY_POLL_SECONDS", 0.01)

    fake_session = MagicMock()
    fake_session.session_id = "sess_stalled_fallback"
    create_session_mock = AsyncMock(return_value=fake_session)
    monkeypatch.setattr(streaming_api.hls_streaming, "create_session", create_session_mock)

    response = client.post("/api/streaming/hls/4.1")

    assert response.status_code == 200
    body = response.json()
    assert "recording_id" not in body
    release_mock.assert_awaited_once()
    assert create_session_mock.await_args.kwargs["stdin_pipe"] is False


def test_stream_channel_hls_for_cast_returns_token_scoped_playlist_url(client, tmp_db, monkeypatch):
    """A Google Cast sender passes for_cast=true - the response must hand
    back a playlist_url under the cast-token path (api/hls.py's
    verify_cast_token routes), not the cookie/bearer-gated one, since the
    actual fetcher is the Cast receiver device."""
    _configure_tuner("software")
    monkeypatch.setattr(watch, "start_fallback_capture", AsyncMock(return_value=None))

    fake_session = MagicMock()
    fake_session.session_id = "sess_cast"
    create_session_mock = AsyncMock(return_value=fake_session)
    monkeypatch.setattr(streaming_api.hls_streaming, "create_session", create_session_mock)

    response = client.post("/api/streaming/hls/4.1?for_cast=true")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "sess_cast"
    assert body["playlist_url"].startswith("/api/hls/sess_cast/")
    assert body["playlist_url"].endswith("/playlist.m3u8")
    assert body["playlist_url"] != "/api/hls/sess_cast/playlist.m3u8"
    cast_token = create_session_mock.await_args.kwargs["cast_token"]
    assert cast_token is not None
    assert body["playlist_url"] == f"/api/hls/sess_cast/{cast_token}/playlist.m3u8"


def test_stream_channel_hls_without_for_cast_omits_cast_token(client, tmp_db, monkeypatch):
    """Default (native Apple client) behavior must stay byte-for-byte
    unchanged - no cast_token minted, existing playlist_url shape."""
    _configure_tuner("software")
    monkeypatch.setattr(watch, "start_fallback_capture", AsyncMock(return_value=None))

    fake_session = MagicMock()
    fake_session.session_id = "sess_native"
    create_session_mock = AsyncMock(return_value=fake_session)
    monkeypatch.setattr(streaming_api.hls_streaming, "create_session", create_session_mock)

    response = client.post("/api/streaming/hls/4.1")

    assert response.status_code == 200
    body = response.json()
    assert body["playlist_url"] == "/api/hls/sess_native/playlist.m3u8"
    assert create_session_mock.await_args.kwargs["cast_token"] is None


def test_stream_channel_with_audio_index_passes_mapping(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    fake_proc = MagicMock()
    fake_proc.stdout.read = AsyncMock(side_effect=[b"ts_data", b""])
    fake_proc.wait = AsyncMock(return_value=0)
    fake_proc.returncode = 0
    create_subproc = AsyncMock(return_value=fake_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subproc)

    response = client.get("/api/streaming/stream/4.1?audio_index=1")
    assert response.status_code == 200
    cmd_args = list(create_subproc.call_args[0])
    assert "-map" in cmd_args
    assert "0:v:0" in cmd_args
    assert "0:a:1" in cmd_args


def test_stream_channel_hls_with_audio_index_passes_mapping(client, tmp_db, monkeypatch):
    _configure_tuner("software")
    monkeypatch.setattr(watch, "start_fallback_capture", AsyncMock(return_value=None))

    fake_session = MagicMock()
    fake_session.session_id = "sess_audio"
    create_session_mock = AsyncMock(return_value=fake_session)
    monkeypatch.setattr(streaming_api.hls_streaming, "create_session", create_session_mock)

    response = client.post("/api/streaming/hls/4.1?audio_index=1")
    assert response.status_code == 200
    ffmpeg_args = create_session_mock.await_args.args[2]
    assert "-map" in ffmpeg_args
    assert "0:v:0" in ffmpeg_args
    assert "0:a:1" in ffmpeg_args

