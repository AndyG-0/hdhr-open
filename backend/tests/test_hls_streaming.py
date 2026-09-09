from __future__ import annotations

import asyncio
import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import hls_streaming


@pytest.fixture(autouse=True)
def _reset_sessions():
    """_sessions is a process-wide singleton (the same one the real app
    uses), so tests must not leak active state between each other."""
    hls_streaming._sessions.clear()
    yield
    hls_streaming._sessions.clear()


def _fake_ffmpeg_process(*, returncode: int | None = None) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.terminate = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    return proc


def _write_playlist(tmp_dir, segments: int = 1) -> None:
    body = b"#EXTM3U\n" + b"#EXTINF:2.0,\nsegment00000.ts\n" * segments
    hls_streaming.playlist_path(tmp_dir).write_bytes(body)


async def _make_session(monkeypatch, *, label: str = "test") -> hls_streaming.HLSSession:
    spawn = AsyncMock(side_effect=lambda *a, **kw: _fake_ffmpeg_process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    session_id, tmp_dir = hls_streaming.allocate_session_dir()
    _write_playlist(tmp_dir)
    return await hls_streaming.create_session(session_id, tmp_dir, [], label=label)


# --- create_session -----------------------------------------------------


async def test_create_session_success_registers_and_keeps_dir(monkeypatch):
    session = await _make_session(monkeypatch)
    assert hls_streaming._sessions[session.session_id] is session
    assert session.tmp_dir.exists()


async def test_create_session_file_not_found_cleans_up(monkeypatch):
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError()))
    session_id, tmp_dir = hls_streaming.allocate_session_dir()

    with pytest.raises(hls_streaming.HLSStartupError):
        await hls_streaming.create_session(session_id, tmp_dir, [], label="test")

    assert not tmp_dir.exists()
    assert session_id not in hls_streaming._sessions


async def test_create_session_playlist_never_appears_cleans_up(monkeypatch):
    monkeypatch.setattr(hls_streaming, "FFMPEG_STARTUP_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(hls_streaming, "HLS_CUSHION_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(hls_streaming, "_PLAYLIST_POLL_SECONDS", 0.01)

    process = _fake_ffmpeg_process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=lambda *a, **kw: process))
    session_id, tmp_dir = hls_streaming.allocate_session_dir()

    with pytest.raises(hls_streaming.HLSStartupError):
        await hls_streaming.create_session(session_id, tmp_dir, [], label="test")

    assert not tmp_dir.exists()
    assert session_id not in hls_streaming._sessions
    process.terminate.assert_called_once()


async def test_create_session_on_process_spawned_raising_cleans_up(monkeypatch):
    process = _fake_ffmpeg_process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=lambda *a, **kw: process))
    session_id, tmp_dir = hls_streaming.allocate_session_dir()

    def _boom(_process):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await hls_streaming.create_session(session_id, tmp_dir, [], label="test", on_process_spawned=_boom)

    assert not tmp_dir.exists()
    assert session_id not in hls_streaming._sessions
    process.terminate.assert_called_once()


async def test_create_session_cancelled_mid_poll_cleans_up(monkeypatch):
    process = _fake_ffmpeg_process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=lambda *a, **kw: process))
    session_id, tmp_dir = hls_streaming.allocate_session_dir()

    task = asyncio.create_task(hls_streaming.create_session(session_id, tmp_dir, [], label="test"))
    # Let the task actually enter the playlist-readiness poll loop before
    # cancelling it, so this exercises cancellation of the `await
    # asyncio.sleep(...)` inside the loop, not cancellation before spawn.
    for _ in range(5):
        await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert not tmp_dir.exists()
    assert session_id not in hls_streaming._sessions
    process.terminate.assert_called_once()


# --- teardown_session -----------------------------------------------------


async def test_teardown_session_removes_dir_and_process(monkeypatch):
    session = await _make_session(monkeypatch)

    await hls_streaming.teardown_session(session.session_id)

    assert session.session_id not in hls_streaming._sessions
    assert not session.tmp_dir.exists()
    session.process.terminate.assert_called_once()


async def test_teardown_session_unknown_id_is_noop():
    await hls_streaming.teardown_session("does-not-exist")


async def test_teardown_session_fires_on_teardown(monkeypatch):
    on_teardown = AsyncMock()
    process = _fake_ffmpeg_process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=lambda *a, **kw: process))
    session_id, tmp_dir = hls_streaming.allocate_session_dir()
    _write_playlist(tmp_dir)
    session = await hls_streaming.create_session(session_id, tmp_dir, [], label="test", on_teardown=on_teardown)

    await hls_streaming.teardown_session(session.session_id)

    on_teardown.assert_awaited_once()


async def test_teardown_session_swallows_on_teardown_error(monkeypatch):
    on_teardown = AsyncMock(side_effect=RuntimeError("boom"))
    process = _fake_ffmpeg_process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(side_effect=lambda *a, **kw: process))
    session_id, tmp_dir = hls_streaming.allocate_session_dir()
    _write_playlist(tmp_dir)
    session = await hls_streaming.create_session(session_id, tmp_dir, [], label="test", on_teardown=on_teardown)

    await hls_streaming.teardown_session(session.session_id)

    on_teardown.assert_awaited_once()
    assert session.session_id not in hls_streaming._sessions
    assert not session.tmp_dir.exists()


async def test_teardown_session_stops_pump(monkeypatch):
    session = await _make_session(monkeypatch)
    pump_stop_event = asyncio.Event()

    async def _pump():
        await pump_stop_event.wait()

    pump_task = asyncio.create_task(_pump())
    await hls_streaming.attach_pump(session.session_id, pump_task, pump_stop_event)

    await hls_streaming.teardown_session(session.session_id)

    assert pump_stop_event.is_set()
    assert pump_task.done()


# --- teardown_all_sessions -------------------------------------------------


async def test_teardown_all_sessions_tears_down_every_session(monkeypatch):
    session_a = await _make_session(monkeypatch, label="a")
    session_b = await _make_session(monkeypatch, label="b")

    await hls_streaming.teardown_all_sessions()

    assert hls_streaming._sessions == {}
    assert not session_a.tmp_dir.exists()
    assert not session_b.tmp_dir.exists()


async def test_teardown_all_sessions_isolates_one_failure(monkeypatch):
    session_a = await _make_session(monkeypatch, label="a")
    session_b = await _make_session(monkeypatch, label="b")
    session_a.process.terminate.side_effect = RuntimeError("boom")

    await hls_streaming.teardown_all_sessions()

    assert hls_streaming._sessions == {}
    assert not session_b.tmp_dir.exists()


async def test_teardown_all_sessions_empty_is_noop():
    await hls_streaming.teardown_all_sessions()


# --- sweep_session_dir_on_startup ------------------------------------------


async def test_sweep_session_dir_on_startup_removes_stray_dirs():
    stray_a = hls_streaming.HLS_SESSION_DIR / "stray-a"
    stray_b = hls_streaming.HLS_SESSION_DIR / "stray-b"
    stray_a.mkdir()
    stray_b.mkdir()
    stray_file = hls_streaming.HLS_SESSION_DIR / "not-a-dir.txt"
    stray_file.write_text("leave me alone")

    await hls_streaming.sweep_session_dir_on_startup()

    assert not stray_a.exists()
    assert not stray_b.exists()
    assert stray_file.exists()


async def test_sweep_session_dir_on_startup_missing_dir_is_noop(monkeypatch, tmp_path):
    monkeypatch.setattr(hls_streaming, "HLS_SESSION_DIR", tmp_path / "does-not-exist")
    await hls_streaming.sweep_session_dir_on_startup()


# --- sweep_orphaned_session_dirs -------------------------------------------


async def test_sweep_orphaned_session_dirs_leaves_tracked_session_alone(monkeypatch):
    session = await _make_session(monkeypatch)
    old = time.time() - hls_streaming.ORPHAN_SESSION_DIR_GRACE_SECONDS - 60
    os.utime(session.tmp_dir, (old, old))

    await hls_streaming.sweep_orphaned_session_dirs()

    assert session.tmp_dir.exists()


async def test_sweep_orphaned_session_dirs_leaves_young_untracked_dir_alone():
    fresh = hls_streaming.HLS_SESSION_DIR / "untracked-fresh"
    fresh.mkdir()

    await hls_streaming.sweep_orphaned_session_dirs()

    assert fresh.exists()


async def test_sweep_orphaned_session_dirs_removes_old_untracked_dir():
    stale = hls_streaming.HLS_SESSION_DIR / "untracked-stale"
    stale.mkdir()
    old = time.time() - hls_streaming.ORPHAN_SESSION_DIR_GRACE_SECONDS - 60
    os.utime(stale, (old, old))

    await hls_streaming.sweep_orphaned_session_dirs()

    assert not stale.exists()


async def test_sweep_orphaned_session_dirs_ignores_non_directory_entries():
    stray_file = hls_streaming.HLS_SESSION_DIR / "not-a-dir.txt"
    stray_file.write_text("leave me alone")

    await hls_streaming.sweep_orphaned_session_dirs()

    assert stray_file.exists()


# --- cast token / URL builders ---------------------------------------------


def test_new_cast_token_is_random_and_urlsafe():
    a = hls_streaming.new_cast_token()
    b = hls_streaming.new_cast_token()
    assert a != b
    assert len(a) > 16


def test_cast_base_url_embeds_session_id_and_token():
    assert hls_streaming.cast_base_url("sess123", "tok456") == "/api/hls/sess123/tok456/"


def test_cast_playlist_url_appends_playlist_filename():
    assert hls_streaming.cast_playlist_url("sess123", "tok456") == "/api/hls/sess123/tok456/playlist.m3u8"


def test_cast_playlist_url_for_request_leaves_real_host_relative():
    # A real hostname/IP means PUBLIC_API_BASE_URL is (or should be) already
    # correctly configured by the operator - this machine's own auto-detected
    # interface must never override that.
    url = hls_streaming.cast_playlist_url_for_request("http://192.168.1.50:8000/", "sess123", "tok456")
    assert url == "/api/hls/sess123/tok456/playlist.m3u8"


def test_cast_playlist_url_for_request_resolves_localhost_to_lan_ip(monkeypatch):
    # localhost in the URL handed to a Cast *receiver* (a separate physical
    # device) means the receiver itself, not this server - the exact bug
    # reported against CAST-1's initial web implementation.
    monkeypatch.setattr(hls_streaming, "_lan_ip", lambda: "10.0.0.5")
    url = hls_streaming.cast_playlist_url_for_request("http://localhost:8000/", "sess123", "tok456")
    assert url == "http://10.0.0.5:8000/api/hls/sess123/tok456/playlist.m3u8"


def test_cast_playlist_url_for_request_resolves_127_0_0_1(monkeypatch):
    monkeypatch.setattr(hls_streaming, "_lan_ip", lambda: "10.0.0.5")
    url = hls_streaming.cast_playlist_url_for_request("http://127.0.0.1:8000/", "sess123", "tok456")
    assert url == "http://10.0.0.5:8000/api/hls/sess123/tok456/playlist.m3u8"


def test_cast_playlist_url_for_request_falls_back_when_lan_ip_undetectable(monkeypatch):
    monkeypatch.setattr(hls_streaming, "_lan_ip", lambda: None)
    url = hls_streaming.cast_playlist_url_for_request("http://localhost:8000/", "sess123", "tok456")
    assert url == "/api/hls/sess123/tok456/playlist.m3u8"


async def test_create_session_stores_cast_token(monkeypatch):
    spawn = AsyncMock(side_effect=lambda *a, **kw: _fake_ffmpeg_process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    session_id, tmp_dir = hls_streaming.allocate_session_dir()
    _write_playlist(tmp_dir)

    session = await hls_streaming.create_session(session_id, tmp_dir, [], label="test", cast_token="tok456")

    assert session.cast_token == "tok456"


async def test_create_session_defaults_cast_token_to_none(monkeypatch):
    session = await _make_session(monkeypatch)
    assert session.cast_token is None


# --- register ---------------------------------------------------------


def test_register_adds_both_jobs():
    scheduler = MagicMock()
    hls_streaming.register(scheduler)

    job_ids = [call.kwargs["id"] for call in scheduler.add_job.call_args_list]
    assert "hls_streaming_reap_idle_sessions" in job_ids
    assert "hls_streaming_sweep_orphaned_session_dirs" in job_ids


# --- touch & reap_idle_sessions ---------------------------------------


async def test_touch_updates_last_request_at(monkeypatch):
    session = await _make_session(monkeypatch)
    session.last_request_at = 100.0

    updated = await hls_streaming.touch(session.session_id)
    assert updated is session
    assert session.last_request_at > 100.0


async def test_touch_unknown_session_returns_none():
    assert await hls_streaming.touch("unknown") is None


async def test_reap_idle_sessions_reaps_stale_sessions(monkeypatch):
    session = await _make_session(monkeypatch)
    session.last_request_at = time.time() - hls_streaming.HLS_IDLE_TIMEOUT_SECONDS - 10

    await hls_streaming.reap_idle_sessions()

    assert session.session_id not in hls_streaming._sessions
    assert not session.tmp_dir.exists()


async def test_reap_idle_sessions_keeps_fresh_sessions(monkeypatch):
    session = await _make_session(monkeypatch)
    session.last_request_at = time.time()

    await hls_streaming.reap_idle_sessions()

    assert session.session_id in hls_streaming._sessions
    assert session.tmp_dir.exists()

