from __future__ import annotations

import asyncio
import logging
import time

from app.dvr import media_cache


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


def test_escape_movie_filter_url_escapes_colons_in_addition_to_quotes_and_backslashes():
    # The movie filter's own option parser splits on the first unescaped ':'
    # after the filename to find ":options" - even inside single quotes - so
    # an http:// URL's scheme/port colons must be escaped or everything past
    # them (including query params) gets silently mis-parsed as filter
    # options and ffmpeg opens no video at all.
    escaped = media_cache._escape_movie_filter_url("http://192.168.50.197:50000/recorded/play?id=abc")
    assert escaped == "http\\://192.168.50.197\\:50000/recorded/play?id=abc"


def test_escape_movie_filter_url_escapes_backslash_and_quote():
    escaped = media_cache._escape_movie_filter_url(r"C:\weird'file.mpg")
    assert escaped == r"C\:\\weird\'file.mpg"


async def test_generate_captions_vtt_builds_argv_with_escaped_colons(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)

    captured_argv: list[str] = []

    async def fake_exec(*argv, **kwargs):
        captured_argv.extend(argv)
        # Simulate a successful ffmpeg run that wrote the output file.
        out_path = argv[-1]
        with open(out_path, "w") as f:
            f.write("WEBVTT\n")
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_cache.generate_captions_vtt("http://192.168.50.197:50000/recorded/play?id=abc", "rec1")

    assert result is not None
    assert result.read_text() == "WEBVTT\n"
    movie_arg = next(a for a in captured_argv if a.startswith("movie="))
    assert "192.168.50.197\\:50000" in movie_arg
    assert "http\\://" in movie_arg


async def test_generate_captions_vtt_does_not_permanently_cache_a_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(media_cache, "_GENERATE_TIMEOUT_SECONDS", 0.01)

    class _HangingProcess(_FakeProcess):
        async def communicate(self, input: bytes | None = None):
            import asyncio

            await asyncio.sleep(10)
            return b"", b""

    async def fake_exec(*argv, **kwargs):
        return _HangingProcess()

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_cache.generate_captions_vtt("url", "rec1")

    assert result is None
    cache_path = tmp_path / "rec1.vtt"
    assert not cache_path.exists()


async def test_generate_captions_vtt_caches_a_genuine_no_captions_result(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)

    async def fake_exec(*argv, **kwargs):
        # ffmpeg exits 0 but writes nothing - a genuine "no captions" run.
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_cache.generate_captions_vtt("url", "rec1")

    assert result is None
    cache_path = tmp_path / "rec1.vtt"
    assert cache_path.exists()
    assert cache_path.stat().st_size == 0


async def test_generate_captions_vtt_uses_cached_file_on_second_call(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    cache_path = tmp_path / "rec1.vtt"
    cache_path.write_text("WEBVTT\n")

    async def fake_exec(*argv, **kwargs):
        raise AssertionError("should not re-run ffmpeg when a cached result exists")

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_cache.generate_captions_vtt("url", "rec1")

    assert result == cache_path


async def test_generate_captions_vtt_coalesces_concurrent_calls(monkeypatch, tmp_path):
    # CC-4 added a second (eager, on-recording-finish) trigger for the same
    # generate_captions_vtt() a client's lazy on-request fetch already calls -
    # without coalescing, both could see the cache missing and race ffmpeg
    # against the same tmp_path.
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    media_cache._generate_captions_inflight.clear()

    call_count = 0
    release = asyncio.Event()

    async def fake_exec(*argv, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise AssertionError("ffmpeg should only be invoked once for concurrent callers")
        await release.wait()
        out_path = argv[-1]
        with open(out_path, "w") as f:
            f.write("WEBVTT\n")
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    task1 = asyncio.create_task(media_cache.generate_captions_vtt("url", "rec1"))
    task2 = asyncio.create_task(media_cache.generate_captions_vtt("url", "rec1"))
    await asyncio.sleep(0.01)  # let both reach generate_captions_vtt's in-flight check

    release.set()
    result1, result2 = await asyncio.wait_for(asyncio.gather(task1, task2), timeout=1.0)

    assert call_count == 1
    assert result1 is not None
    assert result1 == result2
    assert "rec1" not in media_cache._generate_captions_inflight


async def test_generate_captions_vtt_strips_cc_transparent_space_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)

    async def fake_exec(*argv, **kwargs):
        out_path = argv[-1]
        with open(out_path, "w") as f:
            f.write("WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n\\hHello\\h\\hworld\\h\n\n")
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_cache.generate_captions_vtt("url", "rec1")

    assert result is not None
    assert "\\h" not in result.read_text()
    assert "Hello world" in result.read_text()


def test_parse_vtt_timestamp_supports_various_formats():
    assert media_cache._parse_vtt_timestamp("00:00:01.000") == 1.0
    assert media_cache._parse_vtt_timestamp("01:02:03.456") == 3723.456
    assert media_cache._parse_vtt_timestamp("00:05.123") == 5.123
    assert media_cache._parse_vtt_timestamp("12:34.500") == 754.5
    assert media_cache._parse_vtt_timestamp("12.345") == 12.345


def test_parse_vtt_cues_parses_multiple_cues_and_skips_header():
    vtt = "\n".join(
        [
            "WEBVTT",
            "",
            "00:01.000 --> 00:03.500",
            "Hello there",
            "",
            "01:00:04.000 --> 01:00:06.000",
            "Multi-line",
            "cue text",
            "",
        ]
    )
    cues = media_cache._parse_vtt_cues(vtt)
    assert cues == [
        (1.0, 3.5, "Hello there"),
        (3604.0, 3606.0, "Multi-line\ncue text"),
    ]


def test_append_live_cues_writes_header_only_once(tmp_path):
    output_path = tmp_path / "rec1.live.vtt"
    media_cache._append_live_cues(output_path, [(0.0, 2.0, "First")])
    media_cache._append_live_cues(output_path, [(2.0, 4.0, "Second")])

    text = output_path.read_text()
    assert text.count("WEBVTT") == 1
    assert "First" in text
    assert "Second" in text


def test_parse_vtt_block_parses_single_cue():
    block = "00:00:05.000 --> 00:00:07.000\nHi"
    assert media_cache._parse_vtt_block(block) == (5.0, 7.0, "Hi")


def test_parse_vtt_block_returns_none_for_header_or_missing_timing():
    assert media_cache._parse_vtt_block("WEBVTT") is None
    assert media_cache._parse_vtt_block("just text, no arrow here") is None


def test_parse_vtt_block_strips_cc_transparent_space_artifacts():
    # ffmpeg's CEA-608 decoder renders the "transparent space" special
    # character as the literal ASS override sequence "\h" (doubled for the
    # double-width form); the webvtt muxer passes it through unchanged.
    block = "00:00:05.000 --> 00:00:07.000\n\\hHello\\h\\hworld\\h"
    assert media_cache._parse_vtt_block(block) == (5.0, 7.0, "Hello world")


def test_strip_cc_control_artifacts_preserves_multiline_text():
    text = "\\hLine one\nLine\\htwo\\h\\h"
    assert media_cache._strip_cc_control_artifacts(text) == "Line one\nLine two"


def test_parse_srt_block_parses_single_cue():
    block = "1\n00:00:05,000 --> 00:00:07,000\nHi"
    assert media_cache._parse_srt_block(block) == (5.0, 7.0, "Hi")


def test_parse_srt_block_returns_none_for_missing_timing():
    assert media_cache._parse_srt_block("just text, no arrow here") is None


def test_parse_srt_block_skips_cea_708_font_tagged_track():
    # ccextractor emits CEA-708 alongside CEA-608 (when both exist in the
    # source) as font-tagged SRT blocks - only the plain 608 track is wanted
    # for live captions, so a font-tagged block is dropped entirely rather
    # than parsed with tags stripped.
    block = '1\n00:00:05,000 --> 00:00:07,000\n<font color="#aaaaaa">Hi</font>'
    assert media_cache._parse_srt_block(block) is None


def test_parse_srt_block_parses_multiline_cue():
    block = "1\n00:00:05,000 --> 00:00:07,000\nFirst line\nSecond line"
    assert media_cache._parse_srt_block(block) == (5.0, 7.0, "First line\nSecond line")


async def test_ensure_live_captions_is_idempotent(monkeypatch):
    started = []

    async def fake_loop(recording_id, file_path, is_source_alive, capture_start_ts=None, channel=1):
        started.append(recording_id)
        await asyncio.sleep(3600)

    monkeypatch.setattr(media_cache, "_run_live_caption_loop", fake_loop)
    media_cache._live_caption_tasks.clear()

    media_cache.ensure_live_captions("rec1", None, lambda: True)
    media_cache.ensure_live_captions("rec1", None, lambda: True)
    await asyncio.sleep(0)  # let the scheduled task actually start running

    assert len(started) == 1  # second call must not schedule a second loop
    assert ("rec1", 1) in media_cache._live_caption_tasks

    media_cache.stop_live_captions("rec1")
    assert ("rec1", 1) not in media_cache._live_caption_tasks


async def test_run_live_caption_process_once_parses_cues_incrementally_across_reads(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    output_path = tmp_path / "rec1.live.vtt"

    fake_process = _FakeCaptionProcess()

    async def fake_exec(*argv, **kwargs):
        return fake_process

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    pump_started = asyncio.Event()

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        pump_started.set()
        while not stop_event.is_set():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(media_cache, "pump_tail_follow", fake_pump)

    task = asyncio.create_task(
        media_cache._run_live_caption_process_once(tmp_path / "capture.ts", output_path, lambda: True)
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
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    output_path = tmp_path / "rec1.live.vtt"

    fake_process = _FakeCaptionProcess()

    async def fake_exec(*argv, **kwargs):
        return fake_process

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    pump_started = asyncio.Event()

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        pump_started.set()
        while not stop_event.is_set():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(media_cache, "pump_tail_follow", fake_pump)
    caplog.set_level(logging.DEBUG, logger="app.dvr.media_cache")

    capture_start_ts = time.time() - 5.0  # cue ends at t=2s, so ~3s of "lag" by the time it arrives
    task = asyncio.create_task(
        media_cache._run_live_caption_process_once(
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
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_TERMINATE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    fake_process = _FakeCaptionProcess()

    async def fake_exec(*argv, **kwargs):
        return fake_process

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        while not stop_event.is_set() and is_source_alive():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(media_cache, "pump_tail_follow", fake_pump)

    alive = True

    def is_source_alive() -> bool:
        return alive

    media_cache._live_caption_tasks.clear()
    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", is_source_alive)
    await asyncio.sleep(0.02)

    alive = False
    await asyncio.sleep(0.3)

    assert ("rec1", 1) not in media_cache._live_caption_tasks
    assert fake_process.terminated


async def test_live_caption_loop_restarts_when_process_exits_early(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_POLL_SECONDS", 0.01)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_TERMINATE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    processes: list[_FakeCaptionProcess] = []

    async def fake_exec(*argv, **kwargs):
        proc = _FakeCaptionProcess()
        processes.append(proc)
        return proc

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        while not stop_event.is_set() and is_source_alive():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(media_cache, "pump_tail_follow", fake_pump)

    alive = True

    def is_source_alive() -> bool:
        return alive

    media_cache._live_caption_tasks.clear()
    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", is_source_alive)
    await asyncio.sleep(0.02)

    # Simulate the first process crashing on its own (source still alive):
    # its stdout pipe closes and it exits non-zero.
    processes[0].stdout.close()
    processes[0].returncode = 1
    await asyncio.sleep(0.2)

    assert len(processes) >= 2  # the supervisor spawned a fresh attempt

    alive = False
    await asyncio.sleep(0.3)
    assert ("rec1", 1) not in media_cache._live_caption_tasks


async def test_live_caption_loop_passes_capture_start_ts_through(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_MIN_START_BYTES", 0)
    received: list[float | None] = []

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        received.append(capture_start_ts)
        return False  # stop the loop after one run

    monkeypatch.setattr(media_cache, "_run_live_caption_process_once", fake_process_once)

    media_cache._live_caption_tasks.clear()
    capture_start_ts = 12345.0
    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, capture_start_ts)
    await asyncio.sleep(0.05)

    assert received == [capture_start_ts]


async def test_live_caption_loop_logs_restart_cost(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_POLL_SECONDS", 0.01)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    call_count = 0

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        nonlocal call_count
        call_count += 1
        return call_count < 2  # restart once, then stop

    monkeypatch.setattr(media_cache, "_run_live_caption_process_once", fake_process_once)
    caplog.set_level(logging.WARNING, logger="app.dvr.media_cache")

    media_cache._live_caption_tasks.clear()
    capture_start_ts = time.time() - 42.0
    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, capture_start_ts)
    await asyncio.sleep(0.1)

    assert "restarting from byte 0" in caplog.text
    assert "into the capture" in caplog.text


async def test_live_caption_loop_truncates_output_on_restart_avoiding_duplicates(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_POLL_SECONDS", 0.01)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_TERMINATE_TIMEOUT_SECONDS", 0.1)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    processes: list[_FakeCaptionProcess] = []

    async def fake_exec(*argv, **kwargs):
        proc = _FakeCaptionProcess()
        processes.append(proc)
        return proc

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        while not stop_event.is_set() and is_source_alive():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(media_cache, "pump_tail_follow", fake_pump)

    alive = True

    def is_source_alive() -> bool:
        return alive

    media_cache._live_caption_tasks.clear()
    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", is_source_alive)

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

    output_path = media_cache.live_captions_path("rec1")
    text = output_path.read_text()
    assert text.count("First") == 1
    assert ("rec1", 1) not in media_cache._live_caption_tasks


async def test_run_live_caption_process_once_cue_silence_watchdog_trips(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    # Cue-silence budget much tighter than the raw stdout-stall one, so a
    # process that keeps dribbling bytes without ever completing a "\n\n"
    # cue block trips the cue-silence watchdog, not the stall one.
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_CUE_SILENCE_SECONDS", 0.05)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_STDOUT_STALL_SECONDS", 10.0)
    output_path = tmp_path / "rec1.live.vtt"

    fake_process = _FakeCaptionProcess()

    async def fake_exec(*argv, **kwargs):
        return fake_process

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    pump_started = asyncio.Event()

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        pump_started.set()
        while not stop_event.is_set():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(media_cache, "pump_tail_follow", fake_pump)
    caplog.set_level(logging.WARNING, logger="app.dvr.media_cache")

    task = asyncio.create_task(
        media_cache._run_live_caption_process_once(tmp_path / "capture.ts", output_path, lambda: True)
    )
    await pump_started.wait()

    # Bytes keep flowing but never complete a cue block.
    fake_process.stdout.push(b"1\npartial-no-terminator")

    should_restart = await asyncio.wait_for(task, timeout=2.0)

    assert should_restart is True
    assert "completed no cue" in caplog.text
    assert not output_path.exists() or "Hi" not in output_path.read_text()


async def test_live_caption_loop_backoff_schedule_and_circuit_breaker(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(media_cache.asyncio, "sleep", fake_sleep)

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        return True  # "should restart", finishing instantly every time (a quick failure)

    monkeypatch.setattr(media_cache, "_run_live_caption_process_once", fake_process_once)
    caplog.set_level(logging.ERROR, logger="app.dvr.media_cache")

    media_cache._live_caption_tasks.clear()
    media_cache._live_caption_disabled.clear()
    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True)

    await asyncio.wait_for(media_cache._live_caption_tasks[("rec1", 1)], timeout=1.0)

    # POLL_SECONDS(2.0) * 2**n capped at MAX_BACKOFF(120.0), for n=1..7 -
    # the 8th consecutive quick failure trips the circuit breaker before a
    # further backoff/sleep is scheduled.
    assert sleeps == [4.0, 8.0, 16.0, 32.0, 64.0, 120.0, 120.0]
    assert ("rec1", 1) in media_cache._live_caption_disabled
    assert "giving up" in caplog.text.lower()


async def test_ensure_live_captions_noop_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    media_cache._live_caption_tasks.clear()
    media_cache._live_caption_disabled.clear()
    media_cache._live_caption_disabled.add(("rec1", 1))

    started = []

    async def fake_loop(recording_id, file_path, is_source_alive, capture_start_ts=None, channel=1):
        started.append(recording_id)

    monkeypatch.setattr(media_cache, "_run_live_caption_loop", fake_loop)

    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True)
    await asyncio.sleep(0)

    assert started == []
    assert ("rec1", 1) not in media_cache._live_caption_tasks

    media_cache._live_caption_disabled.discard(("rec1", 1))


def test_stop_live_captions_clears_disabled_flag():
    media_cache._live_caption_tasks.clear()
    media_cache._live_caption_disabled.clear()
    media_cache._live_caption_disabled.add(("rec1", 1))

    media_cache.stop_live_captions("rec1")

    assert ("rec1", 1) not in media_cache._live_caption_disabled


async def test_stop_live_captions_cancellation_terminates_process(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    fake_process = _FakeCaptionProcess()

    async def fake_exec(*argv, **kwargs):
        return fake_process

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        while not stop_event.is_set():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(media_cache, "pump_tail_follow", fake_pump)

    media_cache._live_caption_tasks.clear()
    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True)
    await asyncio.sleep(0.02)

    media_cache.stop_live_captions("rec1")
    await asyncio.sleep(0.1)

    assert fake_process.terminated
    assert ("rec1", 1) not in media_cache._live_caption_tasks


async def test_run_live_caption_process_once_uses_channel_flag_and_output_path(monkeypatch, tmp_path):
    # CC-14: channel 2 must decode CEA-608 field/channel 2 (`-2`), not the
    # default channel 1 (`-1`), and its cues land in the channel-2 sidecar.
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    output_path = tmp_path / "rec1.cc2.live.vtt"

    fake_process = _FakeCaptionProcess()
    captured_argv: list[str] = []

    async def fake_exec(*argv, **kwargs):
        captured_argv.extend(argv)
        return fake_process

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    async def fake_pump(file_path, writer, stop_event, is_source_alive, start_offset_bytes=None):
        while not stop_event.is_set():
            await asyncio.sleep(0.005)

    monkeypatch.setattr(media_cache, "pump_tail_follow", fake_pump)

    task = asyncio.create_task(
        media_cache._run_live_caption_process_once(
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
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_MIN_START_BYTES", 0)

    received_channels: list[int] = []

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        received_channels.append(channel)
        return False  # stop after one attempt

    monkeypatch.setattr(media_cache, "_run_live_caption_process_once", fake_process_once)

    media_cache._live_caption_tasks.clear()
    media_cache._live_caption_disabled.clear()

    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, channel=1)
    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, channel=2)

    task1 = media_cache._live_caption_tasks[("rec1", 1)]
    task2 = media_cache._live_caption_tasks[("rec1", 2)]

    await asyncio.wait_for(task1, timeout=1.0)
    await asyncio.wait_for(task2, timeout=1.0)

    assert sorted(received_channels) == [1, 2]
    assert media_cache.live_captions_path("rec1", channel=1) == tmp_path / "rec1.live.vtt"
    assert media_cache.live_captions_path("rec1", channel=2) == tmp_path / "rec1.cc2.live.vtt"


async def test_channel2_with_no_cues_reports_unavailable_after_grace_period(monkeypatch, tmp_path):
    # CC-14: an absent channel-2 track isn't a crash - ccextractor stays
    # alive and just never completes a cue - so this must resolve to
    # "unavailable" via the grace period rather than restarting forever.
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_MIN_START_BYTES", 0)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_TRACK2_GRACE_SECONDS", 0.05)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_POLL_SECONDS", 0.01)

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        await asyncio.sleep(0.02)
        return True  # process died, source still alive - normally would restart

    monkeypatch.setattr(media_cache, "_run_live_caption_process_once", fake_process_once)

    media_cache._live_caption_tasks.clear()
    media_cache._live_caption_disabled.clear()

    assert media_cache.live_caption_track2_status("rec1") is None  # never requested yet

    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, channel=2)
    await asyncio.sleep(0.03)
    assert media_cache.live_caption_track2_status("rec1") == "unknown"

    await asyncio.wait_for(media_cache._live_caption_tasks[("rec1", 2)], timeout=1.0)

    assert media_cache.live_caption_track2_status("rec1") == "unavailable"
    assert ("rec1", 2) in media_cache._live_caption_disabled


async def test_channel2_status_flips_to_available_once_a_cue_lands(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_MIN_START_BYTES", 0)
    monkeypatch.setattr(media_cache, "_LIVE_CAPTION_TRACK2_GRACE_SECONDS", 0.05)

    async def fake_process_once(file_path, output_path, is_source_alive, capture_start_ts=None, channel=1):
        media_cache._append_live_cues(output_path, [(5.0, 7.0, "Segunda")])
        await asyncio.sleep(0.2)  # stay "running" well past the grace period
        return False

    monkeypatch.setattr(media_cache, "_run_live_caption_process_once", fake_process_once)

    media_cache._live_caption_tasks.clear()
    media_cache._live_caption_disabled.clear()

    media_cache.ensure_live_captions("rec1", tmp_path / "capture.ts", lambda: True, channel=2)
    await asyncio.sleep(0.1)

    assert media_cache.live_caption_track2_status("rec1") == "available"
    assert ("rec1", 2) not in media_cache._live_caption_disabled

    media_cache.stop_live_captions("rec1")


async def test_generate_poster_builds_argv_with_image2_and_caches_result(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)

    captured_argv: list[list[str]] = []

    async def fake_exec(*argv, **kwargs):
        captured_argv.append(list(argv))
        # Simulate writing jpeg data to the output path
        out_path = argv[-1]
        with open(out_path, "wb") as f:
            f.write(b"JPEGDATA")
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_cache.generate_poster("/path/to/video.ts", "rec1", offset_seconds=10.0)

    assert result is not None
    assert result == tmp_path / "rec1.poster.jpg"
    assert result.read_bytes() == b"JPEGDATA"

    # Verify ffmpeg arguments
    assert len(captured_argv) == 1
    argv = captured_argv[0]
    assert "-f" in argv
    f_idx = argv.index("-f")
    assert argv[f_idx + 1] == "image2"
    assert "-ss" in argv
    assert "10.0" in argv

    # Calling a second time should return cached path without executing ffmpeg again
    result_cached = await media_cache.generate_poster("/path/to/video.ts", "rec1")
    assert result_cached == result
    assert len(captured_argv) == 1


async def test_generate_poster_falls_back_to_start_on_offset_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)

    captured_argv: list[list[str]] = []

    async def fake_exec(*argv, **kwargs):
        captured_argv.append(list(argv))
        # Fail on first attempt (10s seek), succeed on fallback (0s seek)
        if len(captured_argv) == 1:
            return _FakeProcess(returncode=1)
        out_path = argv[-1]
        with open(out_path, "wb") as f:
            f.write(b"FALLBACK_JPEG")
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_cache.generate_poster("/path/to/short_video.ts", "rec_short", offset_seconds=10.0)

    assert result is not None
    assert result.read_bytes() == b"FALLBACK_JPEG"
    assert len(captured_argv) == 2
    assert "-ss" in captured_argv[1]
    assert captured_argv[1][captured_argv[1].index("-ss") + 1] == "0"


async def test_generate_thumbnail_sprite_builds_argv_with_image2(monkeypatch, tmp_path):
    monkeypatch.setattr(media_cache, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)

    captured_argv: list[list[str]] = []

    async def fake_exec(*argv, **kwargs):
        captured_argv.append(list(argv))
        out_path = argv[-1]
        with open(out_path, "wb") as f:
            f.write(b"SPRITEDATA")
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(media_cache.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_cache.generate_thumbnail_sprite("/path/to/video.ts", "rec1", duration_seconds=600.0)

    assert result is not None
    jpg_path, vtt_path = result
    assert jpg_path == tmp_path / "rec1.jpg"
    assert vtt_path == tmp_path / "rec1.thumbs.vtt"
    assert jpg_path.read_bytes() == b"SPRITEDATA"
    assert vtt_path.exists()

    assert len(captured_argv) == 1
    argv = captured_argv[0]
    assert "-f" in argv
    f_idx = argv.index("-f")
    assert argv[f_idx + 1] == "image2"

