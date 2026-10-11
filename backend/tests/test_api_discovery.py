from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import discovery as discovery_api
from app.auth import get_current_user


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(discovery_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "user", "role": "user"}
    return TestClient(app)


def _item(title: str, image_url: str | None) -> dict:
    return {
        "title": title,
        "bucket": "shows",
        "source": "personalized",
        "channel_number": "4.1",
        "start": None,
        "end": None,
        "episode_title": None,
        "image_url": image_url,
    }


def test_get_discovery_returns_disabled_shape_without_backfill(client, monkeypatch, tmp_db):
    monkeypatch.setattr(discovery_api, "resolve_discovery_enabled", lambda: False)
    backfill = AsyncMock()
    monkeypatch.setattr(discovery_api.poster_lookup, "backfill_missing_images", backfill)

    response = client.get("/api/discovery")

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "has_profile": False, "items": []}
    backfill.assert_not_awaited()


def test_get_discovery_backfills_missing_images_in_response(client, monkeypatch, tmp_db):
    monkeypatch.setattr(discovery_api, "resolve_discovery_enabled", lambda: True)
    monkeypatch.setattr(discovery_api, "resolve_poster_backfill_enabled", lambda: True)
    items = [_item("Has Image", "https://example.com/existing.jpg"), _item("Missing Image", None)]
    monkeypatch.setattr(
        discovery_api.discovery,
        "get_discovery_recommendations",
        lambda: {"has_profile": True, "items": items},
    )

    async def fake_backfill(rows, *, write_back=None):
        for row in rows:
            if not row.get("image_url"):
                row["image_url"] = "https://example.com/backfilled.jpg"
        return 1

    monkeypatch.setattr(discovery_api.poster_lookup, "backfill_missing_images", fake_backfill)

    response = client.get("/api/discovery")

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["image_url"] == "https://example.com/existing.jpg"
    assert body["items"][1]["image_url"] == "https://example.com/backfilled.jpg"


def test_get_discovery_skips_backfill_when_disabled(client, monkeypatch, tmp_db):
    monkeypatch.setattr(discovery_api, "resolve_discovery_enabled", lambda: True)
    monkeypatch.setattr(discovery_api, "resolve_poster_backfill_enabled", lambda: False)
    items = [_item("Missing Image", None)]
    monkeypatch.setattr(
        discovery_api.discovery,
        "get_discovery_recommendations",
        lambda: {"has_profile": True, "items": items},
    )
    backfill = AsyncMock()
    monkeypatch.setattr(discovery_api.poster_lookup, "backfill_missing_images", backfill)

    response = client.get("/api/discovery")

    assert response.status_code == 200
    assert response.json()["items"][0]["image_url"] is None
    backfill.assert_not_awaited()
