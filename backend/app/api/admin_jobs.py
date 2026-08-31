"""Admin-only job registry + run-history API. Lists the jobs registered via
app/jobs.py (both APScheduler interval jobs and event-driven ones) alongside
their recent runs.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends

from app.auth import get_current_admin
from app.jobs import list_job_definitions
from app.storage.db import list_job_runs

router = APIRouter(prefix="/api/admin/jobs", tags=["admin"])

_RECENT_RUNS_LIMIT = 10


@router.get("")
async def list_jobs(_: dict[str, Any] = Depends(get_current_admin)):
    jobs = []
    for definition in list_job_definitions():
        runs = await asyncio.to_thread(list_job_runs, definition.id, _RECENT_RUNS_LIMIT)
        jobs.append(
            {
                "id": definition.id,
                "name": definition.name,
                "description": definition.description,
                "trigger": definition.trigger,
                "recent_runs": runs,
            }
        )
    return jobs
