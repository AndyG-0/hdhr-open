"""Retention policy and disk space management for the builtin DVR.

Enforces per-rule episode retention limits (max_episodes_to_keep), safeguards
minimum free space in RECORDINGS_DIR, and provides safe local recording deletion.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from app.config import HDHOMERUN_MEDIA_CACHE_DIR, RECORDINGS_DIR
from app.storage import db

logger = logging.getLogger(__name__)

DEFAULT_MIN_FREE_SPACE_BYTES = 5 * 1024 * 1024 * 1024  # 5 GB


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


def delete_local_recording_sync(recording_id: str) -> bool:
    """Delete a recording's video file on disk, cache artifacts, and database record."""
    row = db.get_recording(recording_id)
    if not row:
        return False

    file_path_str = row.get("file_path")
    if file_path_str:
        file_path = Path(file_path_str)
        if file_path.exists():
            with contextlib.suppress(Exception):
                file_path.unlink()
                logger.info("Deleted recording file on disk: %s", file_path)

    _clean_media_cache(recording_id)
    db.delete_recording(recording_id)
    logger.info("Deleted recording record [%s] for '%s'", recording_id, row.get("title"))
    return True


async def delete_local_recording(recording_id: str) -> bool:
    """Async wrapper for delete_local_recording_sync."""
    return await asyncio.to_thread(delete_local_recording_sync, recording_id)


def enforce_rule_retention_sync(rule_id: str, max_episodes: int) -> int:
    """Ensure completed recordings for a rule do not exceed max_episodes."""
    if max_episodes <= 0:
        return 0

    rule = db.get_recording_rule(rule_id)
    if not rule:
        return 0

    rule_title = rule.get("title", "").strip().lower()
    all_recordings = db.list_recordings()

    # Find completed recordings matching this rule
    matching: list[dict[str, Any]] = []
    for r in all_recordings:
        if r.get("status") != "completed":
            continue
        if r.get("title", "").strip().lower() == rule_title:
            matching.append(r)

    # Sort oldest first
    matching.sort(key=lambda r: r.get("start_ts", 0))

    excess = len(matching) - max_episodes
    if excess <= 0:
        return 0

    deleted_count = 0
    for r in matching[:excess]:
        if delete_local_recording_sync(r["id"]):
            deleted_count += 1

    logger.info("Enforced retention for rule %s ('%s'): deleted %d old episodes", rule_id, rule_title, deleted_count)
    return deleted_count


def enforce_disk_space_limit_sync(min_free_bytes: int = DEFAULT_MIN_FREE_SPACE_BYTES) -> int:
    """Ensure RECORDINGS_DIR has at least min_free_bytes available."""
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

    all_recordings = [r for r in db.list_recordings() if r.get("status") == "completed"]
    all_recordings.sort(key=lambda r: r.get("start_ts", 0))

    pruned = 0
    for r in all_recordings:
        delete_local_recording_sync(r["id"])
        pruned += 1
        try:
            free_bytes = shutil.disk_usage(RECORDINGS_DIR).free
            if free_bytes >= min_free_bytes:
                break
        except Exception:
            break

    logger.info("Disk space safeguard pruned %d recordings", pruned)
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
