from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import jobs
from app.guide import cleanup as guide_cleanup
from app.storage import db
from app.storage.cache import cache


@pytest.fixture(autouse=True)
def _reset_registry():
    jobs._REGISTRY.clear()
    yield
    jobs._REGISTRY.clear()


def _program_row(channel_id: str, provider: str, start_ts: float, end_ts: float, title: str) -> dict:
    return {
        "channel_id": channel_id,
        "source_provider": provider,
        "external_program_id": None,
        "title": title,
        "episode_title": None,
        "season_number": None,
        "episode_number": None,
        "synopsis": None,
        "start_ts": start_ts,
        "end_ts": end_ts,
        "original_air_date": None,
        "image_url": None,
        "is_new": 0,
        "category": None,
    }


def test_delete_old_guide_programs_purges_across_providers(tmp_db):
    db.upsert_channel("ch1", "1.1", "Channel 1", False)
    db.upsert_channel("ch2", "2.1", "Channel 2", False)

    # Cutoff at 1000
    cutoff = 1000.0

    # Old programs (end_ts <= 1000)
    p1 = _program_row("ch1", "hdhomerun_cloud", 500, 800, "Old Cloud")
    p2 = _program_row("ch1", "xmltv", 600, 900, "Old XMLTV")
    p3 = _program_row("ch2", "schedules_direct", 700, 1000, "Old SD at boundary")

    # Current/Future programs (end_ts > 1000)
    p4 = _program_row("ch1", "hdhomerun_cloud", 900, 1200, "Spanning Program")
    p5 = _program_row("ch2", "xmltv", 1100, 1500, "Future XMLTV")

    db.upsert_guide_programs([p1, p2, p3, p4, p5])

    assert len(db.list_guide_programs(["ch1", "ch2"], 0, 2000)) == 5

    deleted = db.delete_old_guide_programs(cutoff)
    assert deleted == 3

    remaining = db.list_guide_programs(["ch1", "ch2"], 0, 2000)
    assert len(remaining) == 2
    remaining_titles = {r["title"] for r in remaining}
    assert remaining_titles == {"Spanning Program", "Future XMLTV"}


def test_get_start_of_today_ts():
    tz_name = "America/New_York"
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    expected_start = datetime(now.year, now.month, now.day, tzinfo=tz).timestamp()

    actual = guide_cleanup.get_start_of_today_ts(tz_name)
    assert actual == expected_start


@pytest.mark.asyncio
async def test_cleanup_old_guide_programs_deletes_yesterdays_airings(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "1.1", "Channel 1", False)
    db.save_app_settings({"timezone": "UTC"})

    start_of_today = guide_cleanup.get_start_of_today_ts("UTC")

    # Yesterday's program
    yesterday_prog = _program_row("ch1", "hdhomerun_cloud", start_of_today - 7200, start_of_today - 3600, "Yesterday")
    # Today's program
    today_prog = _program_row("ch1", "hdhomerun_cloud", start_of_today + 3600, start_of_today + 7200, "Today")

    db.upsert_guide_programs([yesterday_prog, today_prog])

    cache.set("guide:test", "cached_val", 300)
    assert cache.get("guide:test") == "cached_val"

    deleted = await guide_cleanup.cleanup_old_guide_programs()
    assert deleted == 1

    remaining = db.list_guide_programs(["ch1"], 0, start_of_today + 10000)
    assert len(remaining) == 1
    assert remaining[0]["title"] == "Today"
    assert cache.get("guide:test") is None


def test_register_adds_job_to_scheduler_and_registry():
    scheduler = AsyncIOScheduler()
    guide_cleanup.register(scheduler)

    job_def = jobs._REGISTRY.get(guide_cleanup.JOB_ID)
    assert job_def is not None
    assert job_def.name == "Old guide data cleanup"
    assert job_def.trigger == "interval"

    sched_job = scheduler.get_job(guide_cleanup.JOB_ID)
    assert sched_job is not None
