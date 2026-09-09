from __future__ import annotations

import asyncio
import logging
import time

from app.dvr.media import captions_live, shared


class _FakeProcess:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.killed = False

    async def communicate(self, input: bytes | None = None):
        return b"", b""

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> None:
        pass


class _FakeStreamReader:
    """A scriptable stand-in for asyncio.StreamReader: .push(bytes) queues a
    chunk, .read(n) returns queued chunks (ignoring n - tests only ever push
    whole chunks they want read back as a unit), and .close() makes any
    pending or future .read() return b"" (EOF), matching a real pipe closing."""

    def __init__(self) -> None:
        self._chunks: list[bytes] = []
        self._closed = False

    def push(self, data: bytes) -> None:
        self._chunks.append(data)

    def close(self) -> None:
        self._closed = True

    async def read(self, n: int = -1) -> bytes:
        while not self._chunks and not self._closed:
            await asyncio.sleep(0.005)
        if self._chunks:
            return self._chunks.pop(0)
        return b""


class _FakeStreamWriter:
    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


class _FakeCaptionProcess(_FakeProcess):
    """Mimics the asyncio.subprocess.Process shape _run_live_caption_process_once
    needs: controllable stdin/stdout/stderr streams plus a .terminate() that
    behaves like a real terminated process (returncode becomes non-None)."""

    def __init__(self, returncode: int | None = None):
        super().__init__(returncode=returncode)
        self.stdin = _FakeStreamWriter()
        self.stdout = _FakeStreamReader()
        self.stderr = _FakeStreamReader()
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True
        if self.returncode is None:
            self.returncode = 0

    async def wait(self) -> None:
        return None


async def test_ensure_live_captions_is_idempotent(monkeypatch):
    started = []

    async def fake_loop(recording_id, file_path, is_source_alive, capture_start_ts=None, channel=1):
        started.append(recording_id)
        await asyncio.sleep(3600)

    monkeypatch.setattr(captions_live, "_run_live_caption_loop", fake_loop)
    captions_live._live_caption_tasks.clear()

    captions_live.ensure_live_captions("rec1", None, lambda: True)
    captions_live.ensure_live_captions("rec1", None, lambda: True)
    await asyncio.sleep(0)  # let the scheduled task actually start running

    assert len(started) == 1  # second call must not schedule a second loop
    assert ("rec1", 1) in captions_live._live_caption_tasks

    captions_live.stop_live_captions("rec1")
    assert ("rec1", 1) not in captions_live._live_caption_tasks


async def test_run_live_caption_process_once_parses_cues_incrementally_across_reads(monkeypatch, tmp_path):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    output_path = tmp_path / "rec1.live.vtt"

    fake_process = _FakeCaptionProcess()

    async def fake_exec(*argv, **kwargs):
        return fake_process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    pump_started = asyncio.Event()

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        pump_started.set()
        while not stop_event.is_set():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(captions_live, "pump_tail_follow", fake_pump)

    task = asyncio.create_task(
        captions_live._run_live_caption_process_once(tmp_path / "capture.ts", output_path, lambda: True)
    )
    await pump_started.wait()

    # Push a cue split across two stdout reads - the first half has no
    # complete "\n\n"-delimited block yet, so nothing should be written out.
    fake_process.stdout.push(b"1\n00:00:05,000 --> 00:00:07")
    await asyncio.sleep(0.02)
    assert not output_path.exists() or "Hi" not in output_path.read_text()

    fake_process.stdout.push(b",000\nHi\n\n")
    await asyncio.sleep(0.02)
    assert "Hi" in output_path.read_text()

    fake_process.stdout.close()
    await asyncio.wait_for(task, timeout=1.0)


async def test_run_live_caption_process_once_logs_lag_when_capture_start_ts_given(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    output_path = tmp_path / "rec1.live.vtt"

    fake_process = _FakeCaptionProcess()

    async def fake_exec(*argv, **kwargs):
        return fake_process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    pump_started = asyncio.Event()

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        pump_started.set()
        while not stop_event.is_set():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(captions_live, "pump_tail_follow", fake_pump)
    caplog.set_level(logging.DEBUG, logger="app.dvr.media.captions_live")

    capture_start_ts = time.time() - 5.0  # cue ends at t=2s, so ~3s of "lag" by the time it arrives
    task = asyncio.create_task(
        captions_live._run_live_caption_process_once(
            tmp_path / "capture.ts", output_path, lambda: True, capture_start_ts
        )
    )
    await pump_started.wait()

    fake_process.stdout.push(b"1\n00:00:00,000 --> 00:00:02,000\nHi\n\n")
    await asyncio.sleep(0.02)

    fake_process.stdout.close()
    await asyncio.wait_for(task, timeout=1.0)

    assert "lag=" in caplog.text


async def test_live_caption_loop_stops_cleanly_when_source_dies(monkeypatch, tmp_path):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_TERMINATE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    fake_process = _FakeCaptionProcess()

    async def fake_exec(*argv, **kwargs):
        return fake_process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        while not stop_event.is_set() and is_source_alive():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(captions_live, "pump_tail_follow", fake_pump)

    alive = True

    def is_source_alive() -> bool:
        return alive

    captions_live._live_caption_tasks.clear()
    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", is_source_alive)
    await asyncio.sleep(0.02)

    alive = False
    await asyncio.sleep(0.3)

    assert ("rec1", 1) not in captions_live._live_caption_tasks
    assert fake_process.terminated


async def test_live_caption_loop_restarts_when_process_exits_early(monkeypatch, tmp_path):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_POLL_SECONDS", 0.01)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_TERMINATE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    processes: list[_FakeCaptionProcess] = []

    async def fake_exec(*argv, **kwargs):
        proc = _FakeCaptionProcess()
        processes.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        while not stop_event.is_set() and is_source_alive():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(captions_live, "pump_tail_follow", fake_pump)

    alive = True

    def is_source_alive() -> bool:
        return alive

    captions_live._live_caption_tasks.clear()
    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", is_source_alive)
    await asyncio.sleep(0.02)

    # Simulate the first process crashing on its own (source still alive):
    # its stdout pipe closes and it exits non-zero.
    processes[0].stdout.close()
    processes[0].returncode = 1
    await asyncio.sleep(0.2)

    assert len(processes) >= 2  # the supervisor spawned a fresh attempt

    alive = False
    await asyncio.sleep(0.3)
    assert ("rec1", 1) not in captions_live._live_caption_tasks


async def test_live_caption_loop_passes_capture_start_ts_through(monkeypatch, tmp_path):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_MIN_START_BYTES", 0)
    received: list[float | None] = []

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        received.append(capture_start_ts)
        return False  # stop the loop after one run

    monkeypatch.setattr(captions_live, "_run_live_caption_process_once", fake_process_once)

    captions_live._live_caption_tasks.clear()
    capture_start_ts = 12345.0
    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, capture_start_ts)
    await asyncio.sleep(0.05)

    assert received == [capture_start_ts]


async def test_live_caption_loop_logs_restart_cost(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_POLL_SECONDS", 0.01)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    call_count = 0

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        nonlocal call_count
        call_count += 1
        return call_count < 2  # restart once, then stop

    monkeypatch.setattr(captions_live, "_run_live_caption_process_once", fake_process_once)
    caplog.set_level(logging.WARNING, logger="app.dvr.media.captions_live")

    captions_live._live_caption_tasks.clear()
    capture_start_ts = time.time() - 42.0
    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, capture_start_ts)
    await asyncio.sleep(0.1)

    assert "restarting from byte 0" in caplog.text
    assert "into the capture" in caplog.text


async def test_live_caption_loop_truncates_output_on_restart_avoiding_duplicates(monkeypatch, tmp_path):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_POLL_SECONDS", 0.01)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_TERMINATE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    processes: list[_FakeCaptionProcess] = []

    async def fake_exec(*argv, **kwargs):
        proc = _FakeCaptionProcess()
        processes.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        while not stop_event.is_set() and is_source_alive():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(captions_live, "pump_tail_follow", fake_pump)

    alive = True

    def is_source_alive() -> bool:
        return alive

    captions_live._live_caption_tasks.clear()
    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", is_source_alive)

    while not processes:
        await asyncio.sleep(0.005)
    processes[0].stdout.push(b"1\n00:00:01,000 --> 00:00:02,000\nFirst\n\n")
    await asyncio.sleep(0.02)
    # Simulate a crash: the process dies and gets relaunched from byte 0.
    processes[0].stdout.close()
    processes[0].returncode = 1

    while len(processes) < 2:
        await asyncio.sleep(0.005)
    # The restarted process redecodes from the start and reproduces the same
    # cue - the output should not end up with it twice.
    processes[1].stdout.push(b"1\n00:00:01,000 --> 00:00:02,000\nFirst\n\n")
    await asyncio.sleep(0.02)

    alive = False
    await asyncio.sleep(0.3)

    output_path = captions_live.live_captions_path("rec1")
    text = output_path.read_text()
    assert text.count("First") == 1
    assert ("rec1", 1) not in captions_live._live_caption_tasks


async def test_run_live_caption_process_once_cue_silence_watchdog_trips(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    # Cue-silence budget much tighter than the raw stdout-stall one, so a
    # process that keeps dribbling bytes without ever completing a "\n\n"
    # cue block trips the cue-silence watchdog, not the stall one.
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_CUE_SILENCE_SECONDS", 0.05)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_STDOUT_STALL_SECONDS", 10.0)
    output_path = tmp_path / "rec1.live.vtt"

    fake_process = _FakeCaptionProcess()

    async def fake_exec(*argv, **kwargs):
        return fake_process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    pump_started = asyncio.Event()

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        pump_started.set()
        while not stop_event.is_set():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(captions_live, "pump_tail_follow", fake_pump)
    caplog.set_level(logging.WARNING, logger="app.dvr.media.captions_live")

    task = asyncio.create_task(
        captions_live._run_live_caption_process_once(tmp_path / "capture.ts", output_path, lambda: True)
    )
    await pump_started.wait()

    # Bytes keep flowing but never complete a cue block.
    fake_process.stdout.push(b"1\npartial-no-terminator")

    should_restart = await asyncio.wait_for(task, timeout=2.0)

    assert should_restart is True
    assert "completed no cue" in caplog.text
    assert not output_path.exists() or "Hi" not in output_path.read_text()


async def test_live_caption_loop_backoff_schedule_and_circuit_breaker(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        return True  # "should restart", finishing instantly every time (a quick failure)

    monkeypatch.setattr(captions_live, "_run_live_caption_process_once", fake_process_once)
    caplog.set_level(logging.ERROR, logger="app.dvr.media.captions_live")

    captions_live._live_caption_tasks.clear()
    captions_live._live_caption_disabled.clear()
    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True)

    await asyncio.wait_for(captions_live._live_caption_tasks[("rec1", 1)], timeout=1.0)

    # POLL_SECONDS(2.0) * 2**n capped at MAX_BACKOFF(120.0), for n=1..7 -
    # the 8th consecutive quick failure trips the circuit breaker before a
    # further backoff/sleep is scheduled.
    assert sleeps == [4.0, 8.0, 16.0, 32.0, 64.0, 120.0, 120.0]
    assert ("rec1", 1) in captions_live._live_caption_disabled
    assert "giving up" in caplog.text.lower()


async def test_ensure_live_captions_noop_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    captions_live._live_caption_tasks.clear()
    captions_live._live_caption_disabled.clear()
    captions_live._live_caption_disabled.add(("rec1", 1))

    started = []

    async def fake_loop(recording_id, file_path, is_source_alive, capture_start_ts=None, channel=1):
        started.append(recording_id)

    monkeypatch.setattr(captions_live, "_run_live_caption_loop", fake_loop)

    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True)
    await asyncio.sleep(0)

    assert started == []
    assert ("rec1", 1) not in captions_live._live_caption_tasks

    captions_live._live_caption_disabled.discard(("rec1", 1))


def test_stop_live_captions_clears_disabled_flag():
    captions_live._live_caption_tasks.clear()
    captions_live._live_caption_disabled.clear()
    captions_live._live_caption_disabled.add(("rec1", 1))

    captions_live.stop_live_captions("rec1")

    assert ("rec1", 1) not in captions_live._live_caption_disabled


async def test_stop_live_captions_cancellation_terminates_process(monkeypatch, tmp_path):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    fake_process = _FakeCaptionProcess()

    async def fake_exec(*argv, **kwargs):
        return fake_process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        while not stop_event.is_set():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(captions_live, "pump_tail_follow", fake_pump)

    captions_live._live_caption_tasks.clear()
    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True)
    await asyncio.sleep(0.02)

    captions_live.stop_live_captions("rec1")
    await asyncio.sleep(0.1)

    assert fake_process.terminated
    assert ("rec1", 1) not in captions_live._live_caption_tasks


async def test_run_live_caption_process_once_uses_channel_flag_and_output_path(monkeypatch, tmp_path):
    # CC-14: channel 2 must decode CEA-608 field/channel 2 (`-2`), not the
    # default channel 1 (`-1`), and its cues land in the channel-2 sidecar.
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    output_path = tmp_path / "rec1.cc2.live.vtt"

    fake_process = _FakeCaptionProcess()
    captured_argv: list[str] = []

    async def fake_exec(*argv, **kwargs):
        captured_argv.extend(argv)
        return fake_process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        while not stop_event.is_set():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(captions_live, "pump_tail_follow", fake_pump)

    task = asyncio.create_task(
        captions_live._run_live_caption_process_once(
            tmp_path / "capture.ts", output_path, lambda: True, None, 2
        )
    )
    await asyncio.sleep(0.01)

    assert "-2" in captured_argv
    assert "-1" not in captured_argv

    fake_process.stdout.push(b"1\n00:00:05,000 --> 00:00:07,000\nSegunda\n\n")
    await asyncio.sleep(0.02)
    assert "Segunda" in output_path.read_text()

    fake_process.stdout.close()
    await asyncio.wait_for(task, timeout=1.0)


async def test_channel1_and_channel2_loops_run_independently(monkeypatch, tmp_path):
    # CC-14: the two channels' supervision loops for the same recording_id
    # must not collide on task/disabled-set bookkeeping.
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    received_channels: list[int] = []

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        received_channels.append(channel)
        return False  # stop after one attempt

    monkeypatch.setattr(captions_live, "_run_live_caption_process_once", fake_process_once)

    captions_live._live_caption_tasks.clear()
    captions_live._live_caption_disabled.clear()

    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, channel=1)
    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, channel=2)

    task1 = captions_live._live_caption_tasks[("rec1", 1)]
    task2 = captions_live._live_caption_tasks[("rec1", 2)]

    await asyncio.wait_for(task1, timeout=1.0)
    await asyncio.wait_for(task2, timeout=1.0)

    assert sorted(received_channels) == [1, 2]
    assert captions_live.live_captions_path("rec1", channel=1) == tmp_path / "rec1.live.vtt"
    assert captions_live.live_captions_path("rec1", channel=2) == tmp_path / "rec1.cc2.live.vtt"


async def test_channel2_with_no_cues_reports_unavailable_after_grace_period(monkeypatch, tmp_path):
    # CC-14: an absent channel-2 track isn't a crash - ccextractor stays
    # alive and just never completes a cue - so this must resolve to
    # "unavailable" via the grace period rather than restarting forever.
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_MIN_START_BYTES", 0)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_TRACK2_GRACE_SECONDS", 0.05)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_POLL_SECONDS", 0.01)

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        await asyncio.sleep(0.02)
        return True  # process died, source still alive - normally would restart

    monkeypatch.setattr(captions_live, "_run_live_caption_process_once", fake_process_once)

    captions_live._live_caption_tasks.clear()
    captions_live._live_caption_disabled.clear()

    assert captions_live.live_caption_track2_status("rec1") is None  # never requested yet

    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, channel=2)
    await asyncio.sleep(0.03)
    assert captions_live.live_caption_track2_status("rec1") == "unknown"

    await asyncio.wait_for(captions_live._live_caption_tasks[("rec1", 2)], timeout=1.0)

    assert captions_live.live_caption_track2_status("rec1") == "unavailable"
    assert ("rec1", 2) in captions_live._live_caption_disabled


async def test_channel2_status_flips_to_available_once_a_cue_lands(monkeypatch, tmp_path):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_MIN_START_BYTES", 0)
    monkeypatch.setattr(captions_live, "_LIVE_CAPTION_TRACK2_GRACE_SECONDS", 0.05)

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        shared._append_live_cues(output_path, [(5.0, 7.0, "Segunda")])
        await asyncio.sleep(0.2)  # stay "running" well past the grace period
        return False

    monkeypatch.setattr(captions_live, "_run_live_caption_process_once", fake_process_once)

    captions_live._live_caption_tasks.clear()
    captions_live._live_caption_disabled.clear()

    captions_live.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, channel=2)
    await asyncio.sleep(0.1)

    assert captions_live.live_caption_track2_status("rec1") == "available"
    assert ("rec1", 2) not in captions_live._live_caption_disabled

    captions_live.stop_live_captions("rec1")
