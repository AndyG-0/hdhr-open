from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any

# Fire-and-forget tasks (killing ffmpeg, draining stderr, poster backfills,
# etc.) are tracked here purely so asyncio doesn't garbage-collect them
# mid-flight.
_background_tasks: set[asyncio.Task[Any]] = set()


def run_in_background(coro: Coroutine[Any, Any, Any]) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def terminate_process(process: asyncio.subprocess.Process, *, timeout: float) -> None:
    """SIGTERM, wait up to `timeout`, then SIGKILL if it hasn't exited."""
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=timeout)
    except TimeoutError:
        process.kill()
        # The process is already being force-killed - a stray exception from
        # this final wait (e.g. it was reaped elsewhere between kill() and
        # here) shouldn't take down the caller.
        with contextlib.suppress(Exception):
            await process.wait()


def pid_is_alive(pid: int | None) -> bool:
    """Checks a bare OS pid (not an asyncio.subprocess.Process we own) is still
    running - used to find a recording's ffmpeg writer across a backend restart,
    when CapturePipeline's in-memory tracking has been wiped but the orphaned
    process itself is still alive.
    """
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists, just not ours to signal with 0 (e.g. owned by a different
        # user) - still means it's alive.
        return True
    return True


async def terminate_pid(pid: int, *, timeout: float, poll_interval: float = 0.2) -> None:
    """SIGTERM a bare OS pid, wait up to `timeout`, then SIGKILL if it hasn't
    exited. The bare-pid counterpart to `terminate_process`, for a writer
    found via a durably-persisted pid rather than a live asyncio.subprocess.Process
    (see app.api.tuner.terminate_tuner's orphan-recording fallback).
    """
    if not pid_is_alive(pid):
        return
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGTERM)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while pid_is_alive(pid) and loop.time() < deadline:
        await asyncio.sleep(poll_interval)
    if pid_is_alive(pid):
        with contextlib.suppress(ProcessLookupError):
            os.kill(pid, signal.SIGKILL)


async def drain_stderr_tail(
    stderr: asyncio.StreamReader, tail: bytearray, done: asyncio.Event, *, tail_bytes: int
) -> None:
    """Keep reading `stderr` for the process's whole lifetime, keeping only the last `tail_bytes` around.

    ffmpeg writes a steady trickle of log lines to stderr; if nothing reads
    them, the OS pipe buffer eventually fills and ffmpeg blocks on write(),
    silently stalling an otherwise-healthy stream. The retained tail is
    enough to explain a startup failure (bad channel, busy tuner) without
    holding the whole (unbounded) log in memory.
    """
    try:
        while True:
            chunk = await stderr.read(4096)
            if not chunk:
                return
            tail += chunk
            del tail[: max(0, len(tail) - tail_bytes)]
    finally:
        done.set()


@dataclass
class SubprocessResult:
    returncode: int | None
    stdout: bytes
    stderr: bytes
    timed_out: bool
    spawn_error: str | None


async def run_subprocess(
    argv: list[str],
    *,
    timeout: float,
    stdin_bytes: bytes | None = None,
    merge_stderr: bool = False,
    capture_stdout: bool = True,
    capture_stderr: bool = True,
) -> SubprocessResult:
    """Spawn `argv`, optionally feed it `stdin_bytes`, and wait up to `timeout`
    for it to finish via `communicate()` - the bounded, one-shot-in/one-shot-out
    shape shared by every ffmpeg/ffprobe probe or single-file-generate call in
    this codebase (as opposed to a long-running recording/live-caption spawn,
    which owns its own process for the life of a stream and isn't a fit here).

    Never raises: a spawn failure (missing binary, permissions) or a timeout
    both come back as a `SubprocessResult` the caller can inspect, since every
    existing caller already treats "couldn't run this" as just another
    failure outcome to report, not an exception to handle.
    """
    if merge_stderr:
        stderr_target = asyncio.subprocess.STDOUT
    elif capture_stderr:
        stderr_target = asyncio.subprocess.PIPE
    else:
        stderr_target = asyncio.subprocess.DEVNULL

    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE if stdin_bytes is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE if capture_stdout else asyncio.subprocess.DEVNULL,
            stderr=stderr_target,
        )
    except OSError as exc:
        return SubprocessResult(returncode=None, stdout=b"", stderr=b"", timed_out=False, spawn_error=str(exc))

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(stdin_bytes), timeout=timeout)
    except TimeoutError:
        process.kill()
        with contextlib.suppress(Exception):
            await process.wait()
        return SubprocessResult(returncode=None, stdout=b"", stderr=b"", timed_out=True, spawn_error=None)

    return SubprocessResult(
        returncode=process.returncode, stdout=stdout or b"", stderr=stderr or b"", timed_out=False, spawn_error=None
    )
