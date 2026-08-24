"""APScheduler singleton.

Jobs are registered elsewhere against this shared instance — guide-provider
refreshes (app.guide.service) and the builtin DVR engine's rule expansion /
recording start-stop (app.dvr.builtin.scheduler) — and started once from
app.main's lifespan.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()
