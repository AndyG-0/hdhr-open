from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import jobs
from app.api import admin_jobs as admin_jobs_api
from app.auth import get_current_admin, get_current_user
from app.storage import db


@pytest.fixture(autouse=True)
def _reset_registry():
    jobs._REGISTRY.clear()
    yield
    jobs._REGISTRY.clear()


@pytest.fixture
def client(tmp_db):
    app = FastAPI()
    app.include_router(admin_jobs_api.router)
    return TestClient(app)


def _seed_users():
    db.create_user("admin1", "Admin", None, None, None, None, "2026-01-01T00:00:00Z", role="admin")
    db.create_user("member1", "Member", None, None, None, None, "2026-01-02T00:00:00Z", role="member")


def test_list_jobs_requires_a_session(client):
    _seed_users()

    assert client.get("/api/admin/jobs").status_code == 401


def test_list_jobs_rejects_a_non_admin_session(client):
    _seed_users()
    client.app.dependency_overrides[get_current_user] = lambda: db.get_user("member1")

    assert client.get("/api/admin/jobs").status_code == 403


def test_list_jobs_includes_registered_definitions_and_recent_runs(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")
    jobs.register_event_job(job_id="test_job", name="Test Job", description="A test job.")
    db.create_job_run("run1", "test_job", "2026-01-01T00:00:00+00:00")
    db.finish_job_run("run1", "success", "2026-01-01T00:00:05+00:00", None)

    response = client.get("/api/admin/jobs")

    assert response.status_code == 200
    body = {j["id"]: j for j in response.json()}
    assert body["test_job"]["name"] == "Test Job"
    assert body["test_job"]["trigger"] == "event"
    assert len(body["test_job"]["recent_runs"]) == 1
    assert body["test_job"]["recent_runs"][0]["status"] == "success"


def test_list_jobs_includes_definitions_with_no_runs_yet(client):
    _seed_users()
    client.app.dependency_overrides[get_current_admin] = lambda: db.get_user("admin1")
    jobs.register_event_job(job_id="never_run", name="Never Run", description="Hasn't fired yet.")

    response = client.get("/api/admin/jobs")

    assert response.status_code == 200
    body = {j["id"]: j for j in response.json()}
    assert body["never_run"]["recent_runs"] == []
