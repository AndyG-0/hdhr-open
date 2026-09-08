from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import jobs
from app.storage import db


@pytest.fixture(autouse=True)
def _reset_registry():
    jobs._REGISTRY.clear()
    yield
    jobs._REGISTRY.clear()


def test_app_startup_registers_the_hls_and_caption_jobs(tmp_db):
    from app.main import app

    with TestClient(app):
        pass

    registered = {d.id for d in jobs.list_job_definitions()}
    assert "caption_extraction" in registered
    assert "hls_streaming_reap_idle_sessions" in registered
    assert "hls_streaming_sweep_orphaned_session_dirs" in registered
    assert "guide_cleanup_old_programs" in registered


@pytest.mark.asyncio
async def test_run_tracked_writes_a_success_run(tmp_db):
    async def ok() -> None:
        return None

    await jobs._run_tracked("my_job", ok())

    runs = db.list_job_runs("my_job")
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
    assert runs[0]["started_at"]
    assert runs[0]["finished_at"]
    assert runs[0]["error"] is None


@pytest.mark.asyncio
async def test_run_tracked_writes_a_failed_run_and_reraises(tmp_db):
    async def boom() -> None:
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        await jobs._run_tracked("my_job", boom())

    runs = db.list_job_runs("my_job")
    assert len(runs) == 1
    assert runs[0]["status"] == "failed"
    assert runs[0]["error"] == "kaboom"


def test_register_scheduled_job_wraps_func_and_adds_to_scheduler():
    added = {}

    class FakeScheduler:
        def add_job(self, func, trigger, **kwargs):
            added["func"] = func
            added["trigger"] = trigger
            added["kwargs"] = kwargs

    async def noop() -> None:
        return None

    jobs.register_scheduled_job(
        FakeScheduler(),
        job_id="scheduled_job",
        name="Scheduled Job",
        description="A test job.",
        func=noop,
        trigger="interval",
        seconds=10,
    )

    assert added["trigger"] == "interval"
    assert added["kwargs"]["id"] == "scheduled_job"
    assert added["kwargs"]["seconds"] == 10

    definitions = {d.id: d for d in jobs.list_job_definitions()}
    assert definitions["scheduled_job"].trigger == "interval"
    assert definitions["scheduled_job"].name == "Scheduled Job"


def test_register_event_job_adds_definition_without_scheduling():
    jobs.register_event_job(job_id="event_job", name="Event Job", description="A test job.")

    definitions = {d.id: d for d in jobs.list_job_definitions()}
    assert definitions["event_job"].trigger == "event"


def test_trigger_job_now_modifies_next_run_time_when_job_exists():
    modified = {}

    class FakeScheduler:
        def get_job(self, job_id):
            return object()

        def modify_job(self, job_id, **kwargs):
            modified["job_id"] = job_id
            modified["kwargs"] = kwargs

    assert jobs.trigger_job_now(FakeScheduler(), "scheduled_job") is True
    assert modified["job_id"] == "scheduled_job"
    assert "next_run_time" in modified["kwargs"]


def test_trigger_job_now_returns_false_when_job_is_unknown():
    class FakeScheduler:
        def get_job(self, job_id):
            return None

        def modify_job(self, job_id, **kwargs):
            raise AssertionError("modify_job should not be called for an unknown job")

    assert jobs.trigger_job_now(FakeScheduler(), "nonexistent_job") is False


@pytest.mark.asyncio
async def test_run_tracked_in_background_records_history(tmp_db, monkeypatch):
    scheduled: list = []
    monkeypatch.setattr(jobs, "run_in_background", lambda coro: scheduled.append(coro))

    async def work() -> None:
        return None

    jobs.run_tracked_in_background("bg_job", work())

    assert len(scheduled) == 1
    await scheduled[0]

    runs = db.list_job_runs("bg_job")
    assert len(runs) == 1
    assert runs[0]["status"] == "success"
