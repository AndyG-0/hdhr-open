from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_ok(tmp_db):
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_lifespan_initializes_db_and_starts_scheduler(tmp_db):
    from app.scheduler import scheduler

    with TestClient(app):
        assert scheduler.running
        assert scheduler.get_job("guide_refresh_hdhomerun_cloud") is not None
        assert scheduler.get_job("guide_refresh_xmltv") is not None
    assert not scheduler.running
