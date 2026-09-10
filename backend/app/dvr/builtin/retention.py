"""Retention policy and disk space management for the builtin DVR.

Enforces per-rule episode retention limits (max_episodes_to_keep), safeguards
minimum free space in RECORDINGS_DIR, and provides safe local recording deletion.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from pathlib import Path

from app.config import HDHOMERUN_MEDIA_CACHE_DIR, RECORDINGS_DIR
from app.storage import db

logger = logging.getLogger(__name__)

DEFAULT_MIN_FREE_SPACE_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB

# Upper bound on how much of the completed-recordings library
# enforce_disk_space_limit_sync will delete in a single pass, expressed as a
# fraction of what's currently on disk (rounded down, but always at least 1
# so a genuinely full disk still makes progress). A single low-space reading
# - e.g. a transient spike from something unrelated to the DVR - must not be
# able to silently empty the entire library in one run; capping each pass
# means a real, sustained space shortage still gets cleaned up (the job
# reruns every RETENTION_INTERVAL_SECONDS), but a one-off dip only costs part
# of the library, and the loud log line below gives a chance to notice and
# intervene (e.g. free space manually, or grow RECORDINGS_DIR) before more is
# deleted on a later pass.
_MAX_PRUNE_FRACTION_PER_PASS = 0.5


def _clean_media_cache(recording_id: str) -> None:
    """Delete any thumbnail sprites, posters, and captions cached for recording_id."""
    for ext in (
        ".vtt",
        ".jpg",
        ".thumbs.vtt",
        ".vtt.tmp",
        ".jpg.tmp",
        ".live.vtt",
        ".poster.jpg",
        ".poster.jpg.tmp",
    ):
        cached_file = HDHOMERUN_MEDIA_CACHE_DIR / f"{recording_id}{ext}"
        if cached_file.exists():
            with contextlib.suppress(Exception):
                cached_file.unlink()


def delete_local_recording_sync(recording_id: str, reason: str = "user requested") -> bool:
    """Delete a recording's video file on disk, cache artifacts, and database record.

    `reason` is logged verbatim alongside the deletion - every automatic
    deletion path (retention, disk-space safeguard, startup recovery) passes
    a specific one so "why did my recordings disappear" is answerable from
    the persisted log (see app/logging_config.py) instead of having to read
    code to guess which caller ran.
    """
    row = db.get_recording(recording_id)
    if not row:
        return False

    file_path_str = row.get("file_path")
    file_size = row.get("file_size_bytes") or 0
    if file_path_str:
        file_path = Path(file_path_str)
        if file_path.exists():
            with contextlib.suppress(Exception):
                file_path.unlink()
                logger.info("Deleted recording file on disk: %s", file_path)

    _clean_media_cache(recording_id)
    db.delete_recording(recording_id)
    logger.info(
        "Deleted recording [%s] '%s' (%.1f MB, recorded %s) - reason: %s",
        recording_id,
        row.get("title"),
        file_size / (1024 * 1024),
        row.get("start_ts"),
        reason,
    )
    return True


async def delete_local_recording(recording_id: str, reason: str = "user requested") -> bool:
    """Async wrapper for delete_local_recording_sync."""
    return await asyncio.to_thread(delete_local_recording_sync, recording_id, reason)


def enforce_rule_retention_sync(rule_id: str, max_episodes: int) -> int:
    """Ensure completed recordings for a rule do not exceed max_episodes."""
    if max_episodes <= 0:
        return 0

    rule = db.get_recording_rule(rule_id)
    if not rule:
        return 0

    rule_title = rule.get("title", "").strip().lower()
    matching = db.list_completed_recordings_by_title(rule_title)

    excess = len(matching) - max_episodes
    if excess <= 0:
        return 0

    deleted_count = 0
    for r in matching[:excess]:
        reason = f"per-rule retention limit ({max_episodes} episodes) for rule '{rule_title}'"
        if delete_local_recording_sync(r["id"], reason=reason):
            deleted_count += 1

    logger.info("Enforced retention for rule %s ('%s'): deleted %d old episodes", rule_id, rule_title, deleted_count)
    return deleted_count


def enforce_disk_space_limit_sync(min_free_bytes: int = DEFAULT_MIN_FREE_SPACE_BYTES) -> int:
    """Ensure RECORDINGS_DIR has at least min_free_bytes available.

    Deletes oldest completed recordings first. Capped at
    _MAX_PRUNE_FRACTION_PER_PASS of the current library per pass so a single
    low-space reading can't silently empty the entire recordings library in
    one run - if the cap is hit and the drive is still low, this logs loudly
    and stops, waiting for the next scheduled pass rather than continuing.
    """
    if not RECORDINGS_DIR.exists():
        return 0

    try:
        usage = shutil.disk_usage(RECORDINGS_DIR)
        free_bytes = usage.free
    except Exception:
        logger.debug("Could not determine disk usage for %s", RECORDINGS_DIR, exc_info=True)
        return 0

    if free_bytes >= min_free_bytes:
        return 0

    logger.warning(
        "Low disk space on %s: %d GB free (threshold: %d GB). Pruning oldest recordings...",
        RECORDINGS_DIR,
        free_bytes // (1024**3),
        min_free_bytes // (1024**3),
    )

    all_recordings = db.list_completed_recordings()
    if not all_recordings:
        logger.warning(
            "Disk space is low on %s but there are no completed recordings left to prune", RECORDINGS_DIR
        )
        return 0

    max_deletions = max(1, int(len(all_recordings) * _MAX_PRUNE_FRACTION_PER_PASS))

    pruned = 0
    freed_bytes_total = 0
    for r in all_recordings:
        if pruned >= max_deletions:
            logger.error(
                "Disk space safeguard hit its per-pass prune cap (%d of %d completed recordings) while "
                "still low on free space (%d GB free, threshold %d GB) on %s. Stopping this pass rather "
                "than deleting the rest of the library - it will resume on the next scheduled retention "
                "pass if space is still low. Consider freeing space manually or moving RECORDINGS_DIR to "
                "a larger volume.",
                max_deletions,
                len(all_recordings),
                free_bytes // (1024**3),
                min_free_bytes // (1024**3),
                RECORDINGS_DIR,
            )
            break

        size_before = r.get("file_size_bytes") or 0
        if delete_local_recording_sync(
            r["id"],
            reason=f"disk-space safeguard (free space below {min_free_bytes // (1024**3)} GB threshold)",
        ):
            pruned += 1
            freed_bytes_total += size_before

        try:
            free_bytes = shutil.disk_usage(RECORDINGS_DIR).free
            if free_bytes >= min_free_bytes:
                break
        except Exception:
            break

    logger.info(
        "Disk space safeguard pruned %d recording(s) (%.1f MB freed) on %s; %d GB free now",
        pruned,
        freed_bytes_total / (1024**2),
        RECORDINGS_DIR,
        free_bytes // (1024**3),
    )
    return pruned


def run_full_retention_pass_sync() -> None:
    """Run per-rule retention limits followed by disk space safeguard."""
    rules = db.list_recording_rules(provider="builtin")
    for rule in rules:
        max_eps = rule.get("max_episodes_to_keep")
        if max_eps and max_eps > 0:
            enforce_rule_retention_sync(rule["id"], max_eps)

    enforce_disk_space_limit_sync()


async def run_full_retention_pass() -> None:
    """Async wrapper for run_full_retention_pass_sync."""
    await asyncio.to_thread(run_full_retention_pass_sync)
