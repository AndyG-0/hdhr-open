"""Real-time closed captions for in-progress (live) DVR recordings.

captions_static.generate_captions_vtt decodes a whole, finished file in one
continuous pass and is reliable specifically because of that continuity -
the CEA-608/708 decoder inside ffmpeg's `movie` filter builds up roll-up-
mode/PAC state as it goes and never has to guess. That's fine for a
finished recording (no latency requirement), so it stays on ffmpeg.

An earlier version of this *live* path also ran a periodic windowed loop -
spawning a brand-new ffmpeg process every few seconds, each one seeking
cold into the middle of the growing file. Every fresh process started with
no prior decoder state, which produced garbled/repeated text, dropped
captions at window boundaries, and added latency from the segment cadence
itself. The version after that ran a *single* long-lived ffmpeg process per
active capture instead, started once from byte 0 with no seeking, fed the
growing file continuously via pump_tail_follow. That fixed the
garbling/dropping, but measured 3-7s+ (sometimes 10s+) of end-to-end cue
lag: ffmpeg's `movie`/`subcc` lavfi chain can't flush a WebVTT cue until
the roll-up buffer advances, i.e. until the *next* line of dialogue starts
pushing the current one up.

CC-8 (2026-08-31, see backend/scripts/cc8_realtime_caption_spike.py)
measured this precisely against a real local recording, paced to real time
so the numbers reflect actual live latency: ffmpeg's avoidable flush lag
averaged 1.96s (up to 7.7s on longer pauses between lines) on top of
roll-up-format-inherent lag. `ccextractor`'s live/growing-file stream mode
(`-s`) reads the raw CEA-608/708 byte pairs directly and flushes a line the
instant its own carriage-return control code arrives, rather than waiting
on ffmpeg's `subcc` muxer to notice the next line - measured avg delta
~0.0s (noise-level) against a byte-level real-time reference decoder over
the same window. So this now runs a single long-lived `ccextractor`
process per active capture instead of ffmpeg, same pump_tail_follow feed,
same restart-from-byte-0-on-death/hang supervision below - only the decode
step changed. Output is still written as WebVTT (`_append_live_cues`), so
nothing downstream of this file (clients, `live_captions_path`) needed to
change for this swap.

The residual lag inherent to CEA-608/708 roll-up encoding itself (a line
isn't final, even at the broadcaster's encoder, until the next one starts)
is not fixable from the decode side at all - that part really is a fixed
floor, unlike the ffmpeg-specific flush delay above which was reducible.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from app.async_utils import terminate_process
from app.dvr.builtin.tail_follow import pump_tail_follow
from app.dvr.media.shared import _append_live_cues, _cache_dir, _parse_srt_block

logger = logging.getLogger(__name__)

_LIVE_CAPTION_POLL_SECONDS = 2.0  # backoff between a dead/hung process and the next restart attempt
# Watchdog: a legitimately quiet caption stream (no dialogue) is normal and
# must not trigger a restart, so this only fires on total stdout silence,
# not "no cues" - if ccextractor is genuinely still decoding, it stays
# responsive. A live source hiccup (tuner reconnect, signal dropout) can also
# stall the underlying capture file's growth for tens of seconds without
# pump_tail_follow giving up (it tolerates that indefinitely) - that alone
# would look identical to a hung ccextractor process here, so this needs enough
# margin to not mistake one for the other. The cost of raising it is only a
# slower detection of a genuine hang, while the cost of it firing falsely is
# a full, possibly multi-minute re-decode from byte 0.
_LIVE_CAPTION_STDOUT_STALL_SECONDS = 60.0
# A second, longer watchdog distinct from the one above: that one only fires
# on *total* stdout silence, but a wedged WebVTT muxer can keep dribbling
# partial bytes forever without ever completing a "\n\n"-terminated cue
# block, which resets the stall timer indefinitely while producing zero
# cues. This tracks time since the last successfully parsed cue instead.
_LIVE_CAPTION_CUE_SILENCE_SECONDS = 180.0
_LIVE_CAPTION_TERMINATE_TIMEOUT_SECONDS = 5.0
# ccextractor's --stdin `-s` (live/growing-file) mode reliably segfaults if
# it hits EOF (stdin closed) before it's been fed enough bytes - re-verified
# this session (2026-09-09) with an automated crash-boundary bisection
# against 5 real recordings spanning different channels/bitrates/content: the
# cutoff was the *exact same byte count in every one*, 1,048,576 (1MiB) to
# the byte - one byte under crashes 100% of the time, one byte at or over
# never does. That precision (data-independent, identical to the byte across
# unrelated recordings) points to a fixed internal probe/analysis buffer
# inside ccextractor 0.96.5 itself, not anything about caption content or
# stream bitrate. Separately confirmed this is specifically an EOF artifact,
# not "too little data present" in general: feeding the same
# under-1MiB prefix without closing stdin (mirroring how pump_tail_follow
# actually feeds it below - never closes until the source dies) never
# crashed even after several seconds, at any size tested down to 100KB.
# So the real risk this constant guards against is narrow: a source that
# dies (is_source_alive() goes false) before the pipe has carried 1MiB to
# ccextractor, which closes stdin and delivers that early EOF - not the
# ordinary startup case, where pump_tail_follow just keeps blocking for more
# data and never crashes regardless of how little is on disk. 1.5MiB (50%
# margin over the confirmed exact cutoff) keeps that guarantee while cutting
# the previous 4MB figure's startup wait by well over half. A capture is
# well under this size for the first second or two after a viewer tunes in,
# and ensure_live_captions can be reached that early (the player's own
# attach path polls captions immediately). Waiting here avoids ever handing
# ccextractor a too-small input instead of discovering it via the crash-loop
# breaker below, which would otherwise burn all its retries on byte-0
# re-reads of the same too-small prefix and disable captions for the rest of
# the capture before the source ever had a real chance.
_LIVE_CAPTION_MIN_START_BYTES = 1_572_864  # 1.5 MiB

# Escalating backoff + circuit breaker: an attempt that dies this fast is
# treated as a crash-loop signal rather than a legitimate stall/cue-silence
# restart (which by definition takes at least _LIVE_CAPTION_STDOUT_STALL_
# SECONDS to fire), so a source with persistently corrupt/unsupported CC
# data doesn't hot-loop full byte-0 re-decodes forever.
_LIVE_CAPTION_QUICK_FAIL_SECONDS = 10.0
_LIVE_CAPTION_MAX_BACKOFF_SECONDS = 120.0
# 2,4,8,16,32,64,120,120 - roughly 6 minutes of total backoff before giving up.
_LIVE_CAPTION_MAX_CONSECUTIVE_QUICK_FAILURES = 8

# How long a channel-2 (secondary/CC-14) extraction loop waits, once actually
# running, before an all-zero-cues result is treated as "this broadcast has
# no second CC track" rather than "still checking" or "crashed". An absent
# channel isn't a crash - the process stays alive and simply never completes
# a cue block - so it would otherwise never trip the quick-fail breaker above
# and would instead restart forever, burning a full re-decode every stall
# cycle for a track that will never produce anything. 20s (same order of
# magnitude as web's LIVE_CUE_MAX_CATCHUP_SECONDS) is enough for ccextractor
# to have emitted at least one cue if the channel carries any dialogue at
# all. Not used for channel 1, which is assumed present.
_LIVE_CAPTION_TRACK2_GRACE_SECONDS = 20.0

# Background live-caption extraction loops (see ensure_live_captions below),
# keyed by (recording_id, channel) - channel 1 (the primary broadcast
# language) runs eagerly for every capture; channel 2 (CC-14's secondary
# track) is started lazily, only once a client actually asks for it, so the
# two channels' supervision loops for the same recording need independent
# keys rather than colliding on a bare recording_id.
# capture_pipeline.stop_capture() calls stop_live_captions() as its single
# teardown choke point so a finished/torn-down capture never leaves an
# orphaned extraction loop running (either channel).
_live_caption_tasks: dict[tuple[str, int], asyncio.Task[None]] = {}

# (recording_id, channel) pairs for which live captions have been
# permanently given up on for the rest of this capture - either after too
# many consecutive crashes, or (channel 2 only) because the grace period
# above elapsed with no cues. Once a key is here, ensure_live_captions() is a
# no-op for it - otherwise every viewer's poll would immediately re-trigger
# the whole cycle again the moment the loop above exits and pops itself from
# _live_caption_tasks, defeating the breaker. Cleared by stop_live_captions.
_live_caption_disabled: set[tuple[str, int]] = set()

_LIVE_CAPTION_EMPTY_HEADER_SIZE = len(b"WEBVTT\n\n")


def stop_live_captions(recording_id: str) -> None:
    """Cancel every live-caption extraction loop (every channel) for recording_id, if running."""
    for key in [key for key in _live_caption_tasks if key[0] == recording_id]:
        task = _live_caption_tasks.pop(key, None)
        if task and not task.done():
            task.cancel()
    _live_caption_disabled.difference_update({key for key in _live_caption_disabled if key[0] == recording_id})


def _live_caption_output_has_cues(path: Path) -> bool:
    """Whether path has grown past the bare WEBVTT header written by
    `_reset_live_caption_output` - i.e. at least one cue has been appended."""
    try:
        return path.stat().st_size > _LIVE_CAPTION_EMPTY_HEADER_SIZE
    except OSError:
        return False


def _live_caption_path(recording_id: str, channel: int = 1) -> Path:
    if channel == 1:
        return _cache_dir() / f"{recording_id}.live.vtt"
    return _cache_dir() / f"{recording_id}.cc{channel}.live.vtt"


def live_captions_path(recording_id: str, channel: int = 1) -> Path:
    """Where ensure_live_captions writes recording_id's growing captions
    file for the given channel (1 = primary, 2 = CC-14 secondary track).
    Created (with just a WEBVTT header) as soon as the extraction loop
    starts - callers should still check .exists() since that only happens
    once the loop has actually been started via ensure_live_captions."""
    return _live_caption_path(recording_id, channel)


def live_caption_track2_status(recording_id: str) -> Literal["unknown", "available", "unavailable"] | None:
    """Status of recording_id's secondary (channel 2) caption track, or None
    if channel 2 has never been requested (via ensure_live_captions(...,
    channel=2)) for this capture. "unknown" means the extraction loop is
    still running and hasn't yet produced a cue or hit the grace period;
    "available"/"unavailable" are permanent for the rest of the capture."""
    key = (recording_id, 2)
    path = _live_caption_path(recording_id, channel=2)
    if _live_caption_output_has_cues(path):
        return "available"
    if key in _live_caption_disabled:
        return "unavailable"
    if key in _live_caption_tasks:
        return "unknown"
    return None


def ensure_live_captions(
    recording_id: str,
    file_path: Path,
    is_source_alive: Callable[[], bool],
    capture_start_ts: float | None = None,
    channel: int = 1,
) -> None:
    """Lazily start the background live-caption extraction loop for
    (recording_id, channel) if one isn't already running. Safe to call on
    every viewer's captions request - a no-op once the loop is already
    going, or once it's been permanently disabled for this capture after too
    many crashes (or, for channel 2, after the no-data grace period)."""
    key = (recording_id, channel)
    if key in _live_caption_tasks or key in _live_caption_disabled:
        return
    task = asyncio.create_task(
        _run_live_caption_loop(recording_id, file_path, is_source_alive, capture_start_ts, channel)
    )
    _live_caption_tasks[key] = task


def _reset_live_caption_output(output_path: Path) -> None:
    with contextlib.suppress(Exception):
        output_path.write_text("WEBVTT\n\n", encoding="utf-8")


async def _run_live_caption_loop(
    recording_id: str,
    file_path: Path,
    is_source_alive: Callable[[], bool],
    capture_start_ts: float | None = None,
    channel: int = 1,
) -> None:
    """Supervise the single long-lived captioning ccextractor process for
    (recording_id, channel) for the lifetime of the capture, restarting it
    (from byte 0 again, with output truncated and regenerated) if it dies or
    hangs while the source is still alive. Backs off exponentially on
    consecutive quick failures and gives up entirely (see
    _live_caption_disabled) after too many, rather than hot-looping full
    byte-0 re-decodes forever against a persistently broken source - or, for
    channel 2 only, after _LIVE_CAPTION_TRACK2_GRACE_SECONDS elapses with no
    cues at all (see _LIVE_CAPTION_TRACK2_GRACE_SECONDS)."""
    key = (recording_id, channel)
    output_path = _live_caption_path(recording_id, channel)
    consecutive_quick_failures = 0

    def _current_size() -> int:
        try:
            return file_path.stat().st_size
        except OSError:
            return 0

    try:
        gate_start = time.monotonic()
        if _current_size() < _LIVE_CAPTION_MIN_START_BYTES:
            logger.info(
                "Live captions for %s: waiting for capture to reach %d bytes before starting "
                "ccextractor (currently %d bytes)",
                recording_id,
                _LIVE_CAPTION_MIN_START_BYTES,
                _current_size(),
            )
        while is_source_alive() and _current_size() < _LIVE_CAPTION_MIN_START_BYTES:
            await asyncio.sleep(_LIVE_CAPTION_POLL_SECONDS)
        if time.monotonic() - gate_start > 0.1:
            logger.info(
                "Live captions for %s: done waiting after %.1fs (size now %d bytes, source_alive=%s)",
                recording_id,
                time.monotonic() - gate_start,
                _current_size(),
                is_source_alive(),
            )
        loop_start = time.monotonic()
        attempt_number = 0
        while is_source_alive():
            attempt_number += 1
            _reset_live_caption_output(output_path)
            attempt_start = time.monotonic()
            logger.info(
                "Live captions for %s channel %d: starting attempt #%d", recording_id, channel, attempt_number
            )
            should_restart = await _run_live_caption_process_once(
                file_path, output_path, is_source_alive, capture_start_ts, channel
            )
            attempt_duration = time.monotonic() - attempt_start

            if attempt_duration < _LIVE_CAPTION_QUICK_FAIL_SECONDS:
                consecutive_quick_failures += 1
            else:
                consecutive_quick_failures = 0

            if (
                channel != 1
                and not _live_caption_output_has_cues(output_path)
                and time.monotonic() - loop_start >= _LIVE_CAPTION_TRACK2_GRACE_SECONDS
            ):
                logger.info(
                    "Live captions for %s channel %d: no cues emitted after %.0fs - treating as "
                    "unavailable rather than continuing to restart",
                    recording_id,
                    channel,
                    time.monotonic() - loop_start,
                )
                _live_caption_disabled.add(key)
                break

            if consecutive_quick_failures >= _LIVE_CAPTION_MAX_CONSECUTIVE_QUICK_FAILURES:
                logger.error(
                    "Live captions disabled for recording %s channel %d after %d consecutive crashes "
                    "within %.0fs of starting each time - giving up for the rest of this "
                    "capture (source likely has corrupted/unsupported caption data)",
                    recording_id,
                    channel,
                    consecutive_quick_failures,
                    _LIVE_CAPTION_QUICK_FAIL_SECONDS,
                )
                _live_caption_disabled.add(key)
                break

            if should_restart and is_source_alive():
                backoff = (
                    min(
                        _LIVE_CAPTION_POLL_SECONDS * (2**consecutive_quick_failures),
                        _LIVE_CAPTION_MAX_BACKOFF_SECONDS,
                    )
                    if consecutive_quick_failures > 0
                    else _LIVE_CAPTION_POLL_SECONDS
                )
                elapsed = (
                    f"{time.time() - capture_start_ts:.0f}s into the capture"
                    if capture_start_ts is not None
                    else "unknown position in capture"
                )
                logger.warning(
                    "Live caption process restarting from byte 0 (%s) - full re-decode required "
                    "(backing off %.0fs, %d consecutive quick failures)",
                    elapsed,
                    backoff,
                    consecutive_quick_failures,
                )
            if not should_restart or not is_source_alive():
                break
            await asyncio.sleep(backoff)
    except asyncio.CancelledError:
        raise
    finally:
        logger.info(
            "Live captions for %s channel %d: loop exiting (source_alive=%s, disabled=%s)",
            recording_id,
            channel,
            is_source_alive(),
            key in _live_caption_disabled,
        )
        _live_caption_tasks.pop(key, None)


async def _drain_stderr_logging(stream: asyncio.StreamReader) -> None:
    """Drain the caption ccextractor process's stderr, logging anything it says.

    `--quiet` keeps this empty in the normal case (verified: it suppresses
    ccextractor's version banner, config dump, and per-run stats summary
    without hiding real errors, unlike `--no-progress-bar` alone which still
    leaves all of that in place), so anything that arrives here is worth
    surfacing - it's the only visibility into *why* a given channel's
    captions come back empty (unsupported input, no CC data, a probe failure
    on the pipe, etc.) instead of just silently producing nothing.
    """
    with contextlib.suppress(Exception):
        while True:
            chunk = await stream.read(4096)
            if not chunk:
                return
            text = chunk.decode("utf-8", errors="replace").strip()
            if text:
                logger.warning("Live caption ccextractor stderr: %s", text)


async def _run_live_caption_process_once(
    file_path: Path,
    output_path: Path,
    is_source_alive: Callable[[], bool],
    capture_start_ts: float | None = None,
    channel: int = 1,
) -> bool:
    """Run one continuous captioning ccextractor process, decoding file_path
    from byte 0 with no seeking, until the source dies, the process exits, or
    stdout goes silent for too long while the source is still alive (a hung
    process). Returns True if the caller should spawn a fresh attempt.

    `-s <huge>` puts ccextractor in live/growing-file stream mode - the same
    mode it'd use tailing a live tuner capture - rather than its default
    behavior of stopping as soon as it catches up to the current end of a
    file it thinks is complete. `--quiet` keeps stderr empty in the normal
    case (see `_drain_stderr_logging`). `-{channel}` restricts decoding to a
    single CEA-608 field/channel (1 = the primary broadcast language, 2 =
    CC-14's secondary track) instead of decoding every CEA-708 (DTVCC)
    service present - which on a dual-language broadcast is often a second
    language (e.g. Spanish SAP) - and interleaving it into this same stdout
    stream alongside the requested 608 track, distinguishable (per
    ccextractor's own behavior) only by a `<font>` tag it isn't guaranteed to
    add to every 708 cue. That let secondary-language lines slip past
    `_parse_srt_block`'s `<font>` filter and appear mixed in with the
    primary caption text."""
    argv = [
        "ccextractor",
        "--stdin",
        "-s",
        "999999999",
        f"-{channel}",
        "-out=srt",
        "-stdout",
        "-o",
        "/dev/null",
        "--quiet",
    ]
    attempt_start = time.monotonic()
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        logger.warning("Could not start live caption ccextractor process")
        return is_source_alive()

    assert process.stdin is not None
    assert process.stdout is not None
    assert process.stderr is not None

    try:
        current_size = file_path.stat().st_size
    except OSError:
        current_size = -1
    logger.info(
        "Live caption ccextractor attempt starting (pid=%s, file=%s, current size=%d bytes)",
        getattr(process, "pid", None),
        file_path,
        current_size,
    )

    pump_stop_event = asyncio.Event()
    pump_task = asyncio.create_task(
        pump_tail_follow(file_path, process.stdin, pump_stop_event, is_source_alive, start_offset_bytes=0)
    )
    drain_task = asyncio.create_task(_drain_stderr_logging(process.stderr))

    stalled = False
    cue_stalled = False
    cues_emitted = 0

    async def stdout_reader() -> None:
        # Never let an exception here go unretrieved - this task is only
        # ever awaited on the cancellation path, so anything raised here
        # instead of returned/logged would otherwise surface as a
        # "Task exception was never retrieved" leak with no diagnostics.
        nonlocal stalled, cue_stalled, cues_emitted
        buffer = ""
        # CEA-608 roll-up mode: ccextractor's SRT output for each cue is a
        # snapshot of the *whole* current on-screen roll-up buffer, not just
        # the newly-completed line - so the still-visible previous line gets
        # re-emitted verbatim as the new cue's first line (confirmed against
        # real broadcast captures: ~75% of consecutive cues share a line this
        # way). The client intentionally keeps a still-open previous cue on
        # screen alongside a newly-arriving one (see caption-controller.ts's
        # roll-up eviction), so passing this repeated line through as well
        # would show it twice at once - which is exactly the "duplicated
        # line" symptom this strips at the source, before it's ever written
        # to the output file.
        last_emitted_line: str | None = None
        lag_samples: list[float] = []
        last_summary_monotonic = time.monotonic()
        last_cue_monotonic = time.monotonic()

        def _record_lag_sample(lag: float) -> None:
            nonlocal last_summary_monotonic
            lag_samples.append(lag)
            now = time.monotonic()
            if now - last_summary_monotonic >= 30.0:
                logger.info(
                    "Live caption lag over last %.0fs: min=%.1fs avg=%.1fs max=%.1fs (n=%d)",
                    now - last_summary_monotonic,
                    min(lag_samples),
                    sum(lag_samples) / len(lag_samples),
                    max(lag_samples),
                    len(lag_samples),
                )
                lag_samples.clear()
                last_summary_monotonic = now

        try:
            while True:
                # Two independent watchdogs share this one read loop: a raw
                # stdout-silence timeout (_LIVE_CAPTION_STDOUT_STALL_SECONDS)
                # and a longer cue-silence timeout
                # (_LIVE_CAPTION_CUE_SILENCE_SECONDS) for a muxer that keeps
                # producing bytes but never completes a cue block. Whichever
                # budget is smaller bounds this read.
                cue_budget_remaining = _LIVE_CAPTION_CUE_SILENCE_SECONDS - (
                    time.monotonic() - last_cue_monotonic
                )
                if cue_budget_remaining <= 0:
                    cue_stalled = True
                    return
                read_timeout = min(_LIVE_CAPTION_STDOUT_STALL_SECONDS, cue_budget_remaining)
                try:
                    chunk = await asyncio.wait_for(process.stdout.read(4096), timeout=read_timeout)
                except TimeoutError:
                    if time.monotonic() - last_cue_monotonic >= _LIVE_CAPTION_CUE_SILENCE_SECONDS:
                        cue_stalled = True
                    else:
                        stalled = True
                    return
                if not chunk:
                    logger.info(
                        "Live caption ccextractor stdout closed (EOF) after %d cues emitted, "
                        "%d bytes left unparsed in buffer",
                        cues_emitted,
                        len(buffer),
                    )
                    return
                # ccextractor's SRT output uses \r\n line endings, unlike
                # ffmpeg's WebVTT - normalize before block-splitting on
                # "\n\n" or a block boundary never matches.
                buffer += chunk.decode("utf-8", errors="replace").replace("\r\n", "\n")
                while "\n\n" in buffer:
                    block, buffer = buffer.split("\n\n", 1)
                    cue = _parse_srt_block(block)
                    if cue is not None:
                        last_cue_monotonic = time.monotonic()
                        start, end, text = cue
                        lines = text.split("\n")
                        if last_emitted_line is not None and lines and lines[0].strip() == last_emitted_line:
                            lines = lines[1:]
                        if not lines:
                            # The whole cue was a repeat of what's already on
                            # screen (no new line at all) - nothing to add.
                            continue
                        last_emitted_line = lines[-1].strip()
                        cue = (start, end, "\n".join(lines))
                        cues_emitted += 1
                        _append_live_cues(output_path, [cue])
                        lag = (time.time() - capture_start_ts) - cue[1] if capture_start_ts is not None else None
                        logger.info(
                            "Live caption cue #%d appended: cue_end=%.1fs lag=%s text=%r",
                            cues_emitted,
                            cue[1],
                            f"{lag:.1f}s" if lag is not None else "n/a",
                            cue[2][:60],
                        )
                        if capture_start_ts is not None:
                            _record_lag_sample(lag)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Live caption ccextractor stdout reader failed", exc_info=True)

    reader_task = asyncio.create_task(stdout_reader())

    async def stop_pump_and_stdin() -> None:
        pump_stop_event.set()
        with contextlib.suppress(Exception):
            await pump_task
        with contextlib.suppress(Exception):
            process.stdin.close()

    try:
        done, _pending = await asyncio.wait({pump_task, reader_task}, return_when=asyncio.FIRST_COMPLETED)
        logger.info(
            "Live caption attempt: %s finished first",
            "pump (source feed)" if pump_task in done else "ccextractor stdout reader",
        )
    except asyncio.CancelledError:
        logger.info(
            "Live caption ccextractor attempt cancelled after %.1fs (cues_emitted=%d) - "
            "caller is tearing down the capture",
            time.monotonic() - attempt_start,
            cues_emitted,
        )
        reader_task.cancel()
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await stop_pump_and_stdin()
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await reader_task
        await terminate_process(process, timeout=_LIVE_CAPTION_TERMINATE_TIMEOUT_SECONDS)
        drain_task.cancel()
        raise

    # Whichever side finished first (source died, or ccextractor exited/stalled
    # on its own), stop the other side and let it wind down before reaping it.
    await stop_pump_and_stdin()
    if not reader_task.done():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(reader_task, timeout=_LIVE_CAPTION_TERMINATE_TIMEOUT_SECONDS)

    exit_code = process.returncode
    await terminate_process(process, timeout=_LIVE_CAPTION_TERMINATE_TIMEOUT_SECONDS)
    drain_task.cancel()
    with contextlib.suppress(Exception, asyncio.CancelledError):
        await drain_task

    if stalled:
        logger.warning(
            "Live caption ccextractor process stalled with no output for %.0fs", _LIVE_CAPTION_STDOUT_STALL_SECONDS
        )
    elif cue_stalled:
        logger.warning(
            "Live caption ccextractor process produced bytes but completed no cue for %.0fs - treating as hung",
            _LIVE_CAPTION_CUE_SILENCE_SECONDS,
        )
    elif exit_code not in (0, None):
        logger.warning("Live caption ccextractor process exited with code %s", exit_code)

    logger.info(
        "Live caption ccextractor attempt ended after %.1fs: exit_code=%s stalled=%s cue_stalled=%s "
        "cues_emitted=%d source_alive=%s",
        time.monotonic() - attempt_start,
        exit_code,
        stalled,
        cue_stalled,
        cues_emitted,
        is_source_alive(),
    )

    return is_source_alive()
