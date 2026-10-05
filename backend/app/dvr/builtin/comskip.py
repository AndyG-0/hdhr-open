"""Daily (or on-demand) commercial-detection sweep over completed builtin-DVR
recordings, via the third-party `comskip` CLI tool.

v1 scope: detection only - comskip writes a `<recording>.edl` cutlist sidecar
next to the recording's video file (comskip's own naming convention, which
matches `p.with_suffix(".edl")` already read by
`app.api.dvr_streaming._load_commercial_segments`). Nothing is cut or
re-encoded, and this never runs against a still-recording file - only
`db.list_completed_recordings()` rows are considered.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import jobs
from app.config import effective_settings, resolve_comskip_mode
from app.storage import db

logger = logging.getLogger(__name__)

JOB_ID = "comskip_sweep"
SWEEP_INTERVAL_SECONDS = 24 * 3600  # 24 hours (daily)
COMSKIP_TIMEOUT_SECONDS = 2 * 3600  # generous ceiling for a single recording
MAX_COMSKIP_ATTEMPTS = 3  # stop retrying a recording that keeps failing on its own merits

_warned_missing_binary = False


def resolve_comskip_enabled(global_mode: str, rule_override: str) -> bool:
    """A per-rule override always wins; 'default' falls back to the global
    policy. See the plan's "Resolved design decisions" for the rationale.
    """
    if rule_override == "always":
        return True
    if rule_override == "never":
        return False
    return global_mode != "none"


async def run_comskip(file_path: Path) -> bool:
    """Spawn comskip against `file_path`, writing its EDL cutlist to the
    same directory (so it lands at `file_path.with_suffix(".edl")`, comskip's
    own convention for naming output after the input's stem). Returns True
    on a zero exit code.
    """
    binary = shutil.which("comskip")
    if binary is None:
        global _warned_missing_binary
        if not _warned_missing_binary:
            logger.warning("comskip binary not found on PATH; skipping commercial detection sweep")
            _warned_missing_binary = True
        return False

    argv = [binary, "--output_edl", str(file_path), str(file_path.parent)]
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        logger.error("Failed to launch comskip for %s: %s", file_path, exc)
        return False

    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=COMSKIP_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        logger.error("comskip timed out after %ds for %s", COMSKIP_TIMEOUT_SECONDS, file_path)
        return False

    # comskip's own exit-code convention: 0 = commercials found, 1 = none
    # found (still a successful run - the EDL may be empty or absent), >1 =
    # an actual failure.
    if process.returncode not in (0, 1):
        logger.warning(
            "comskip exited %s for %s: %s", process.returncode, file_path, stderr.decode(errors="replace")[-2000:]
        )
        return False
    return True


async def run_comskip_sweep() -> None:
    """Run comskip against every completed recording that hasn't been
    evaluated yet, honoring the global `comskip_mode` setting and each
    recording's rule-level override.
    """
    app_settings = await asyncio.to_thread(effective_settings)
    global_mode = resolve_comskip_mode(app_settings.get("comskip_mode"))

    recordings = await asyncio.to_thread(db.list_completed_recordings)
    for recording in recordings:
        status = recording.get("comskip_status")
        attempts = recording.get("comskip_attempts") or 0
        if status is not None and not (status == "failed" and attempts < MAX_COMSKIP_ATTEMPTS):
            continue

        rule_override = await asyncio.to_thread(db.get_comskip_override_for_recording, recording["id"])
        if not resolve_comskip_enabled(global_mode, rule_override):
            await asyncio.to_thread(db.update_recording, recording["id"], comskip_status="skipped")
            continue

        path = Path(recording["file_path"])
        if not path.exists():
            continue

        await asyncio.to_thread(db.update_recording, recording["id"], comskip_status="running")
        ok = await run_comskip(path)
        await asyncio.to_thread(
            db.update_recording,
            recording["id"],
            comskip_status="done" if ok else "failed",
            comskip_attempts=attempts + 1,
        )


def register(scheduler: AsyncIOScheduler) -> None:
    """Register the daily comskip sweep job with APScheduler and the jobs
    registry (the registry's generic "Run now" endpoint doubles as the
    manual trigger - no bespoke admin UI needed for that part).
    """
    jobs.register_scheduled_job(
        scheduler,
        job_id=JOB_ID,
        name="Commercial detection (comskip)",
        description="Runs comskip against completed recordings missing commercial markers.",
        func=run_comskip_sweep,
        trigger="interval",
        seconds=SWEEP_INTERVAL_SECONDS,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
