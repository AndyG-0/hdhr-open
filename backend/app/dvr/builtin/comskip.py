"""Daily (or on-demand) commercial-detection sweep over completed
recordings - from both the builtin DVR and, when configured, the official
HDHomeRun DVR - via the third-party `comskip` CLI tool.

v1 scope: detection only - comskip writes a `<recording>.edl` cutlist sidecar
next to the recording's video file (comskip's own naming convention, which
matches `p.with_suffix(".edl")` already read by
`app.api.dvr_streaming._load_commercial_segments`). Nothing is cut or
re-encoded, and this never runs against a still-recording file.

Builtin-DVR recordings are considered via `db.list_completed_recordings()`.
HDHomeRun-DVR recordings have no row there (that table is scoped to
builtin-produced files only) - they're fetched live from the HDHomeRun
engine's own API and only processed when the admin has pointed
`dvr_recordings_path` at a local mount of that engine's storage; their
status/attempts are tracked separately, in `hdhomerun_comskip_status`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import jobs
from app.config import effective_settings, resolve_comskip_mode
from app.storage import db

logger = logging.getLogger(__name__)

COMSKIP_INI_PATH = Path(__file__).parent / "comskip.ini"

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

    # comskip has no "--output_edl" CLI flag - EDL output is an ini-only
    # setting, so it's enabled via a packaged ini (see comskip.ini) rather
    # than a bare flag that comskip would otherwise reject outright.
    argv = [binary, f"--ini={COMSKIP_INI_PATH}", str(file_path), str(file_path.parent)]
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
    if not file_path.with_suffix(".edl").exists():
        logger.warning("comskip finished for %s but wrote no .edl sidecar", file_path)
    return True


def index_hdhomerun_recordings(recordings_path: str) -> dict[str, list[Path]]:
    """Maps each file's basename under `recordings_path` to its paths. The
    HDHomeRun DVR reports recordings by bare basename, while the recording
    server stores them in show/category subfolders beneath its storage root.
    """
    root = Path(recordings_path).resolve()
    index: dict[str, list[Path]] = {}
    for dirpath, _, filenames in os.walk(root):
        for name in filenames:
            path = Path(dirpath, name).resolve()
            if path.is_relative_to(root):
                index.setdefault(name, []).append(path)
    return index


def resolve_hdhomerun_local_path(
    recordings_path: str, filename: str, index: dict[str, list[Path]] | None = None
) -> Path | None:
    """Locates the local file for `filename`, the HDHomeRun DVR engine's own
    filename for a recording. Tries it as a path relative to
    `recordings_path` first, then falls back to finding a file with the same
    basename anywhere under it (the DVR reports basenames only). Returns
    `None` if nothing matches, or if the basename is ambiguous. Every result
    is inside `recordings_path`: `filename` comes from the HDHomeRun box's
    own API, a trusted LAN device, but a joined path is still checked the
    way `dvr_streaming.py` checks client-supplied paths.
    """
    root = Path(recordings_path).resolve()
    direct = (root / filename).resolve()
    if direct.is_file() and direct.is_relative_to(root):
        return direct

    if index is None:
        index = index_hdhomerun_recordings(str(root))
    matches = index.get(Path(filename).name, [])
    if len(matches) > 1:
        logger.warning("DVR filename %r matches %d files under %s; skipping", filename, len(matches), root)
        return None
    return matches[0] if matches else None


async def _run_hdhomerun_comskip_sweep(global_mode: str) -> None:
    from app.api._dvr_shared import _get_hdhomerun_settings_safe
    from app.integrations import hdhomerun_client

    hdhomerun_settings = await _get_hdhomerun_settings_safe()
    recordings_path = hdhomerun_settings.get("dvr_recordings_path")
    if not recordings_path or not hdhomerun_client.is_dvr_configured(hdhomerun_settings):
        return

    now = time.time()
    index = await asyncio.to_thread(index_hdhomerun_recordings, recordings_path)
    for entry in await hdhomerun_client.fetch_dvr_recordings(hdhomerun_settings):
        filename = entry.get("filename")
        recording_id = entry.get("recording_id")
        record_end = entry.get("record_end")
        if not filename or not recording_id or record_end is None or record_end > now:
            continue  # no file reference, or still recording

        tracked = await asyncio.to_thread(db.get_hdhomerun_comskip_status, recording_id)
        status = tracked.get("status") if tracked else None
        attempts = tracked.get("attempts", 0) if tracked else 0
        if status is not None and not (status == "failed" and attempts < MAX_COMSKIP_ATTEMPTS):
            continue

        # No per-rule comskip_override here: HDHomeRun recording rules live
        # on the HDHomeRun engine's own native rule system, not in this
        # app's `recording_rules` table, so only the global mode applies.
        if not resolve_comskip_enabled(global_mode, "default"):
            await asyncio.to_thread(db.upsert_hdhomerun_comskip_status, recording_id, filename, "skipped", attempts)
            continue

        path = resolve_hdhomerun_local_path(recordings_path, filename, index)
        if path is None:
            logger.warning(
                "HDHomeRun recording %s: no file under %s for DVR filename %r", recording_id, recordings_path, filename
            )
            await asyncio.to_thread(db.upsert_hdhomerun_comskip_status, recording_id, filename, "failed", attempts + 1)
            continue

        await asyncio.to_thread(db.upsert_hdhomerun_comskip_status, recording_id, filename, "running", attempts)
        ok = await run_comskip(path)
        logger.info(
            "HDHomeRun comskip sweep: recording_id=%s filename=%r resolved to %s -> %s",
            recording_id,
            filename,
            path,
            "done" if ok else "failed",
        )
        await asyncio.to_thread(
            db.upsert_hdhomerun_comskip_status,
            recording_id,
            filename,
            "done" if ok else "failed",
            attempts + 1,
        )


async def check_hdhomerun_recordings_mount(settings: dict[str, Any]) -> str:
    """Validates `dvr_recordings_path` the way the sweep will use it: it must
    be a readable, writable directory, and the DVR's own recording filenames
    must resolve to real files under it. Returns a summary on success and
    raises `HDHomeRunError` with the reason otherwise.
    """
    from app.integrations import hdhomerun_client

    recordings_path = settings.get("dvr_recordings_path")
    if not recordings_path:
        raise hdhomerun_client.HDHomeRunError("No recordings path is set.")
    root = Path(recordings_path)
    if not root.is_dir():
        raise hdhomerun_client.HDHomeRunError(f"{recordings_path} is not a directory inside the container.")
    if not os.access(root, os.R_OK | os.X_OK):
        raise hdhomerun_client.HDHomeRunError(f"{recordings_path} is not readable by the backend process.")
    try:
        with tempfile.NamedTemporaryFile(dir=root, prefix=".hdhr-open-mount-check-"):
            pass
    except OSError as exc:
        raise hdhomerun_client.HDHomeRunError(
            f"{recordings_path} is not writable by the backend process ({exc.strerror or exc}). "
            "comskip writes its .edl next to each recording, so the mount needs write access."
        ) from exc

    file_count = sum(len(files) for _, _, files in os.walk(root))
    if file_count == 0:
        raise hdhomerun_client.HDHomeRunError(f"{recordings_path} is readable and writable but contains no files.")

    recordings = await hdhomerun_client.fetch_dvr_recordings(settings)
    sampled = [entry for entry in recordings if entry.get("filename")]
    if not sampled:
        return f"Mounted and writable; {file_count} files found. No DVR recordings to match against."

    index = index_hdhomerun_recordings(recordings_path)
    resolved = 0
    misses: list[str] = []
    for entry in sampled:
        if resolve_hdhomerun_local_path(recordings_path, entry["filename"], index) is not None:
            resolved += 1
        elif len(misses) < 3:
            misses.append(entry["filename"])
    if resolved == 0:
        raise hdhomerun_client.HDHomeRunError(
            f"None of the {len(sampled)} DVR recordings were found under {recordings_path}. "
            f"The DVR reports paths like {misses[0]!r}; check that the mount covers the DVR's storage root."
        )
    detail = f"Mounted and writable; {resolved} of {len(sampled)} DVR recordings found."
    if misses:
        detail += f" Not found, e.g. {', '.join(repr(m) for m in misses)}."
    return detail


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

    await _run_hdhomerun_comskip_sweep(global_mode)


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
