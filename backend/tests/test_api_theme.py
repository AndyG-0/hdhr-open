from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import theme as theme_api
from app.auth import get_current_user


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(theme_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "user1", "role": "member"}
    return TestClient(app)


def test_get_theme_requires_authentication():
    app = FastAPI()
    app.include_router(theme_api.router)
    unauthenticated_client = TestClient(app)
    response = unauthenticated_client.get("/api/theme")
    assert response.status_code == 401


def test_get_theme_returns_theme_list_and_default(client):
    response = client.get("/api/theme")
    assert response.status_code == 200
    data = response.json()
    assert "themes" in data
    assert "default" in data
    assert data["default"] == "dark"
    theme_ids = [t["id"] for t in data["themes"]]
    assert "light" in theme_ids
    assert "dark" in theme_ids
    assert "sepia" in theme_ids
    assert "contrast" in theme_ids
    assert "forest" in theme_ids
    assert "ocean" in theme_ids
