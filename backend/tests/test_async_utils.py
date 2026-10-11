from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import subprocess
import time

import pytest

from app import async_utils


def _spawn(*args: str) -> subprocess.Popen:
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _reap_in_background(proc: subprocess.Popen) -> asyncio.Future:
    """Reaps `proc` on a worker thread as soon as it exits.

    In the real orphan-pid scenario `terminate_pid` is built for, the backend
    process calling it is never the orphan's parent (restarts reparent true
    orphans to init, which reaps them immediately) - but in this test, the
    test process IS the child's parent, so without an active waiter the dead
    child sits as a zombie and pid_is_alive() (kill(pid, 0)) keeps reporting
    it alive, masking how fast terminate_pid actually worked.
    """
    return asyncio.get_event_loop().run_in_executor(None, proc.wait)


def test_pid_is_alive_none_or_zero_is_false():
    assert async_utils.pid_is_alive(None) is False
    assert async_utils.pid_is_alive(0) is False


def test_pid_is_alive_true_for_running_process():
    proc = _spawn("sleep", "30")
    try:
        assert async_utils.pid_is_alive(proc.pid) is True
    finally:
        proc.kill()
        proc.wait()


def test_pid_is_alive_false_for_exited_and_reaped_process():
    proc = _spawn("true")
    proc.wait()  # reap it so the pid is actually released, not just a zombie
    assert async_utils.pid_is_alive(proc.pid) is False


def test_pid_is_alive_true_on_permission_error(monkeypatch):
    def _raise_permission_error(pid, sig):
        raise PermissionError

    monkeypatch.setattr(async_utils.os, "kill", _raise_permission_error)
    assert async_utils.pid_is_alive(12345) is True


@pytest.mark.asyncio
async def test_terminate_pid_noop_if_already_dead():
    proc = _spawn("true")
    proc.wait()
    # Must not raise even though the pid is gone.
    await async_utils.terminate_pid(proc.pid, timeout=5)


@pytest.mark.asyncio
async def test_terminate_pid_sigterm_succeeds_quickly():
    proc = _spawn("sleep", "30")
    reaper = _reap_in_background(proc)
    try:
        start = time.monotonic()
        await async_utils.terminate_pid(proc.pid, timeout=5, poll_interval=0.05)
        elapsed = time.monotonic() - start

        await reaper
        # A plain `sleep` dies on the first SIGTERM - this should return well
        # before the 5s timeout, proving it didn't need to escalate to SIGKILL.
        assert elapsed < 2
    finally:
        proc.wait()


@pytest.mark.asyncio
async def test_terminate_pid_escalates_to_sigkill_when_sigterm_is_ignored():
    # A process that traps SIGTERM can only be stopped by SIGKILL, which
    # can't be trapped - this proves terminate_pid actually escalates rather
    # than giving up after the first signal.
    proc = _spawn("sh", "-c", "trap '' TERM; sleep 30")
    reaper = _reap_in_background(proc)
    try:
        await asyncio.sleep(0.2)  # let the trap get installed before signaling
        start = time.monotonic()
        await async_utils.terminate_pid(proc.pid, timeout=0.5, poll_interval=0.05)
        elapsed = time.monotonic() - start

        await reaper
        # SIGTERM is ignored, so terminate_pid must have waited out the full
        # timeout before escalating to SIGKILL.
        assert elapsed >= 0.5
        assert elapsed < 2
    finally:
        with contextlib.suppress(ProcessLookupError):
            os.kill(proc.pid, signal.SIGKILL)
        proc.wait()
