"""Job registry: wraps background maintenance work - both APScheduler
interval jobs and event-driven fire-and-forget tasks - with run-history
tracking in the `job_runs` table, so `/api/admin/jobs` has something to show
regardless of which style triggers a given job.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.async_utils import run_in_background
from app.storage import db

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobDefinition:
    id: str
    name: str
    description: str
    trigger: str  # "interval" | "event"


_REGISTRY: dict[str, JobDefinition] = {}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _run_tracked(job_id: str, coro: Awaitable[None]) -> None:
    run_id = uuid.uuid4().hex
    await asyncio.to_thread(db.create_job_run, run_id, job_id, _now_iso())
    try:
        await coro
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        await asyncio.to_thread(db.finish_job_run, run_id, "failed", _now_iso(), str(exc))
        raise
    else:
        await asyncio.to_thread(db.finish_job_run, run_id, "success", _now_iso(), None)


def register_scheduled_job(
    scheduler: AsyncIOScheduler,
    *,
    job_id: str,
    name: str,
    description: str,
    func: Callable[[], Awaitable[None]],
    trigger: str,
    **trigger_kwargs: Any,
) -> None:
    """Register `func` with `scheduler` on `trigger` (e.g. "interval",
    seconds=10), wrapping each invocation with run-history tracking."""
    _REGISTRY[job_id] = JobDefinition(id=job_id, name=name, description=description, trigger="interval")

    async def _tracked() -> None:
        await _run_tracked(job_id, func())

    scheduler.add_job(_tracked, trigger, id=job_id, **trigger_kwargs)


def register_event_job(*, job_id: str, name: str, description: str) -> None:
    """Register an event-driven job's identity - no scheduler trigger, it's
    fired ad hoc via `run_tracked_in_background` - so it still shows up in
    the admin listing even before its first run."""
    _REGISTRY[job_id] = JobDefinition(id=job_id, name=name, description=description, trigger="event")


def run_tracked_in_background(job_id: str, coro: Awaitable[None]) -> None:
    """Fire-and-forget `coro`, like `run_in_background`, but recording a
    `job_runs` row for it - for event-driven jobs (e.g. per-recording
    caption extraction) that aren't on an interval trigger."""
    run_in_background(_run_tracked(job_id, coro))


def list_job_definitions() -> list[JobDefinition]:
    return list(_REGISTRY.values())
