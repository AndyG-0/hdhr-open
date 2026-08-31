from __future__ import annotations

import time
import uuid
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import guide as guide_api
from app.auth import get_current_admin, get_current_user
from app.storage import db
from app.storage.db import save_network_integration


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(guide_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role": "member"}
    return TestClient(app)


@pytest.fixture
def admin_client():
    app = FastAPI()
    app.include_router(guide_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role": "admin"}
    app.dependency_overrides[get_current_admin] = lambda: {"id": "u1", "role": "admin"}
    return TestClient(app)



def _configure_tuner(tmp_db):
    save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local", "tuner_port": 80})


def test_get_guide_returns_empty_list_when_no_data(client, tmp_db):
    response = client.get("/api/guide")

    assert response.status_code == 200
    assert response.json() == []


def test_get_guide_returns_persisted_programs(client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()
    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "hdhomerun_cloud",
                "external_program_id": "SH123",
                "title": "Some Show",
                "episode_title": "Pilot",
                "season_number": 1,
                "episode_number": 1,
                "synopsis": "A show begins.",
                "start_ts": now,
                "end_ts": now + 1800,
                "original_air_date": "2020-01-01",
                "image_url": "http://example.com/image.jpg",
                "is_new": 0,
                "category": None,
            }
        ]
    )

    response = client.get("/api/guide")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["channel_number"] == "4.1"
    assert body[0]["channel_name"] == "WNBC"
    assert body[0]["airings"][0]["title"] == "Some Show"
    assert body[0]["airings"][0]["episode_number"] == "1.1"


def test_get_channels_requires_tuner_configured(client, tmp_db):
    response = client.get("/api/guide/channels")
    assert response.status_code == 404


def test_get_channels_merges_lineup_and_guide_with_playback_url(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()
    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "hdhomerun_cloud",
                "external_program_id": "SH123",
                "title": "Some Show",
                "episode_title": None,
                "season_number": None,
                "episode_number": None,
                "synopsis": None,
                "start_ts": now - 60,
                "end_ts": now + 1800,
                "original_air_date": None,
                "image_url": None,
                "is_new": 0,
                "category": None,
            }
        ]
    )
    db.save_guide_provider_state("hdhomerun_cloud", "2026-08-16T00:00:00+00:00")

    channels = [
        {
            "channel_number": "4.1",
            "name": "WNBC",
            "is_hd": True,
            "is_drm": False,
            "stream_url": "http://hdhomerun.local:80/auto/v4.1",
        }
    ]
    monkeypatch.setattr(guide_api.hdhomerun_client, "fetch_lineup", AsyncMock(return_value=channels))

    response = client.get("/api/guide/channels")

    assert response.status_code == 200
    body = response.json()
    assert body["guide_available"] is True
    assert body["channels"][0]["playback_url"] == "/api/streaming/stream/4.1"
    # The raw tuner URL is preserved but isn't what the client should play.
    assert body["channels"][0]["stream_url"] == "http://hdhomerun.local:80/auto/v4.1"
    assert body["channels"][0]["now"]["title"] == "Some Show"


def _program_row(channel_id: str, provider: str, start_ts: float, title: str) -> dict:
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
        "end_ts": start_ts + 1800,
        "original_air_date": None,
        "image_url": None,
        "is_new": 0,
        "category": None,
    }


def test_get_guide_prefers_pinned_provider_when_both_have_data(client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    db.update_channel(channel_id, guide_provider="xmltv")
    now = time.time()
    db.upsert_guide_programs(
        [
            _program_row(channel_id, "hdhomerun_cloud", now, "Cloud Show"),
            _program_row(channel_id, "xmltv", now, "XMLTV Show"),
        ]
    )

    response = client.get("/api/guide")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert [a["title"] for a in body[0]["airings"]] == ["XMLTV Show"]


def test_get_guide_uses_default_priority_when_unpinned(client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()
    db.upsert_guide_programs(
        [
            _program_row(channel_id, "xmltv", now, "XMLTV Show"),
            _program_row(channel_id, "hdhomerun_cloud", now, "Cloud Show"),
        ]
    )

    response = client.get("/api/guide")

    assert response.status_code == 200
    body = response.json()
    assert [a["title"] for a in body[0]["airings"]] == ["XMLTV Show"]


def test_get_guide_respects_custom_configured_priority(client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    db.save_app_settings({"guide_provider_priority": "hdhomerun_cloud,xmltv,schedules_direct"})
    now = time.time()
    db.upsert_guide_programs(
        [
            _program_row(channel_id, "xmltv", now, "XMLTV Show"),
            _program_row(channel_id, "hdhomerun_cloud", now, "Cloud Show"),
        ]
    )

    response = client.get("/api/guide")

    assert response.status_code == 200
    body = response.json()
    assert [a["title"] for a in body[0]["airings"]] == ["Cloud Show"]


def test_get_guide_falls_back_when_pinned_provider_has_no_rows(client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    db.update_channel(channel_id, guide_provider="schedules_direct")
    now = time.time()
    db.upsert_guide_programs([_program_row(channel_id, "hdhomerun_cloud", now, "Cloud Show")])

    response = client.get("/api/guide")

    assert response.status_code == 200
    body = response.json()
    assert [a["title"] for a in body[0]["airings"]] == ["Cloud Show"]


def test_get_channels_now_next_prefers_pinned_provider(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    db.update_channel(channel_id, guide_provider="xmltv")
    now = time.time()
    db.upsert_guide_programs(
        [
            _program_row(channel_id, "hdhomerun_cloud", now - 60, "Cloud Show"),
            _program_row(channel_id, "xmltv", now - 60, "XMLTV Show"),
        ]
    )
    db.save_guide_provider_state("hdhomerun_cloud", "2026-08-16T00:00:00+00:00")

    channels = [
        {
            "channel_number": "4.1",
            "name": "WNBC",
            "is_hd": True,
            "is_drm": False,
            "stream_url": "http://hdhomerun.local:80/auto/v4.1",
        }
    ]
    monkeypatch.setattr(guide_api.hdhomerun_client, "fetch_lineup", AsyncMock(return_value=channels))

    response = client.get("/api/guide/channels")

    assert response.status_code == 200
    body = response.json()
    assert body["channels"][0]["now"]["title"] == "XMLTV Show"


def test_get_channels_now_next_falls_back_when_pinned_provider_has_no_rows(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    db.update_channel(channel_id, guide_provider="xmltv")
    now = time.time()
    db.upsert_guide_programs([_program_row(channel_id, "hdhomerun_cloud", now - 60, "Cloud Show")])
    db.save_guide_provider_state("hdhomerun_cloud", "2026-08-16T00:00:00+00:00")

    channels = [
        {
            "channel_number": "4.1",
            "name": "WNBC",
            "is_hd": True,
            "is_drm": False,
            "stream_url": "http://hdhomerun.local:80/auto/v4.1",
        }
    ]
    monkeypatch.setattr(guide_api.hdhomerun_client, "fetch_lineup", AsyncMock(return_value=channels))

    response = client.get("/api/guide/channels")

    assert response.status_code == 200
    body = response.json()
    assert body["channels"][0]["now"]["title"] == "Cloud Show"


def test_get_channels_guide_unavailable_without_prior_refresh(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    channels = [
        {
            "channel_number": "4.1",
            "name": "WNBC",
            "is_hd": True,
            "is_drm": False,
            "stream_url": "http://hdhomerun.local:80/auto/v4.1",
        }
    ]
    monkeypatch.setattr(guide_api.hdhomerun_client, "fetch_lineup", AsyncMock(return_value=channels))

    response = client.get("/api/guide/channels")

    assert response.status_code == 200
    body = response.json()
    assert body["guide_available"] is False
    assert body["channels"][0]["now"] is None
    assert body["channels"][0]["next"] is None


def test_get_channels_guide_available_with_xmltv_refresh_only(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()
    db.upsert_guide_programs([_program_row(channel_id, "xmltv", now - 60, "XMLTV Show")])
    db.save_guide_provider_state("xmltv", "2026-08-16T00:00:00+00:00")

    channels = [
        {
            "channel_number": "4.1",
            "name": "WNBC",
            "is_hd": True,
            "is_drm": False,
            "stream_url": "http://hdhomerun.local:80/auto/v4.1",
        }
    ]
    monkeypatch.setattr(guide_api.hdhomerun_client, "fetch_lineup", AsyncMock(return_value=channels))

    response = client.get("/api/guide/channels")

    assert response.status_code == 200
    body = response.json()
    assert body["guide_available"] is True
    assert body["channels"][0]["now"]["title"] == "XMLTV Show"


def test_get_channel_settings_empty(client, tmp_db):
    response = client.get("/api/guide/channels/settings")
    assert response.status_code == 200
    assert response.json() == []


def test_get_channel_settings_with_channels_and_mapping(client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    db.update_channel(channel_id, guide_provider="xmltv", is_favorite=1)
    db.upsert_xmltv_channel_map(channel_id, "wnbc.us", "NBC New York")

    response = client.get("/api/guide/channels/settings")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == channel_id
    assert body[0]["channel_number"] == "4.1"
    assert body[0]["name"] == "WNBC"
    assert body[0]["is_hd"] is True
    assert body[0]["is_favorite"] is True
    assert body[0]["hidden"] is False
    assert body[0]["guide_provider"] == "xmltv"
    assert body[0]["xmltv_channel_id"] == "wnbc.us"
    assert body[0]["xmltv_display_name"] == "NBC New York"


def test_update_channel_settings_as_admin(admin_client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)

    response = admin_client.patch(
        f"/api/guide/channels/{channel_id}",
        json={
            "guide_provider": "xmltv",
            "xmltv_channel_id": "I10.1.wnbc.com",
            "xmltv_display_name": "NBC 4 HD",
            "is_favorite": True,
            "hidden": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == channel_id
    assert body["guide_provider"] == "xmltv"
    assert body["xmltv_channel_id"] == "I10.1.wnbc.com"
    assert body["xmltv_display_name"] == "NBC 4 HD"
    assert body["is_favorite"] is True

    # Verify persistence in db
    db_ch = db.get_channel(channel_id)
    assert db_ch["guide_provider"] == "xmltv"
    assert db_ch["is_favorite"] == 1
    db_map = db.get_xmltv_channel_map(channel_id)
    assert db_map["xmltv_channel_id"] == "I10.1.wnbc.com"
    assert db_map["display_name"] == "NBC 4 HD"


def test_update_channel_settings_clear_xmltv_mapping(admin_client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    db.upsert_xmltv_channel_map(channel_id, "wnbc.us", "NBC")

    response = admin_client.patch(
        f"/api/guide/channels/{channel_id}",
        json={
            "guide_provider": None,
            "xmltv_channel_id": "",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["guide_provider"] is None
    assert body["xmltv_channel_id"] is None
    assert body["xmltv_display_name"] is None

    assert db.get_xmltv_channel_map(channel_id) is None


def test_update_channel_settings_as_member_forbidden(client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)

    response = client.patch(
        f"/api/guide/channels/{channel_id}",
        json={"guide_provider": "xmltv"},
    )
    assert response.status_code == 403


def test_update_channel_settings_not_found(admin_client, tmp_db):
    response = admin_client.patch(
        "/api/guide/channels/nonexistent",
        json={"guide_provider": "xmltv"},
    )
    assert response.status_code == 404


def test_get_xmltv_feed_channels(admin_client, tmp_db, monkeypatch):
    save_network_integration("xmltv", "xmltv", "XMLTV", {"url": "http://example.com/guide.xml"})

    xml_data = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<tv generator-info-name="test">'
        '  <channel id="I4.1.wnbc.com">'
        "    <display-name>WNBC</display-name>"
        "    <display-name>4.1 WNBC-HD</display-name>"
        "  </channel>"
        '  <channel id="I5.1.wnyw.com">'
        "    <display-name>FOX 5</display-name>"
        "  </channel>"
        "</tv>"
    )
    from xml.etree import ElementTree
    root = ElementTree.fromstring(xml_data)
    monkeypatch.setattr(guide_api.xmltv, "_fetch_xmltv_root", AsyncMock(return_value=root))

    response = admin_client.get("/api/guide/xmltv-feed-channels")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["xmltv_channel_id"] == "I4.1.wnbc.com"
    assert body[0]["display_names"] == ["WNBC", "4.1 WNBC-HD"]
    assert body[1]["xmltv_channel_id"] == "I5.1.wnyw.com"


def test_refresh_guide(admin_client, tmp_db, monkeypatch):
    mock_refresh_hdhomerun = AsyncMock()
    mock_refresh_xmltv = AsyncMock()
    monkeypatch.setattr(guide_api.service, "refresh_hdhomerun_guide", mock_refresh_hdhomerun)
    monkeypatch.setattr(guide_api.xmltv, "refresh_xmltv_guide", mock_refresh_xmltv)

    response = admin_client.post("/api/guide/refresh")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_get_xmltv_stats_empty(client, tmp_db):
    response = client.get("/api/guide/xmltv/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["url"] is None
    assert data["last_refreshed_at"] is None
    assert data["channels_in_feed"] == 0
    assert data["mapped_channels_count"] == 0
    assert data["programs_count"] == 0
    assert data["days_count"] == 0.0
    assert data["start_date"] is None
    assert data["end_date"] is None


def test_get_xmltv_stats_with_data(client, tmp_db):
    save_network_integration("xmltv", "xmltv", "XMLTV", {"url": "http://example.com/feed.xml"})
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    db.upsert_xmltv_channel_map("ch1", "I4.1.wnbc.com", "WNBC")
    db.save_guide_provider_state("xmltv", "2026-08-22T10:00:00+00:00", '{"channels_in_feed": 25}')
    db.upsert_guide_programs([
        {
            "channel_id": "ch1",
            "source_provider": "xmltv",
            "title": "Morning News",
            "start_ts": 1787300000.0,
            "end_ts": 1787472800.0,
        }
    ])

    response = client.get("/api/guide/xmltv/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["url"] == "http://example.com/feed.xml"
    assert data["last_refreshed_at"] == "2026-08-22T10:00:00+00:00"
    assert data["channels_in_feed"] == 25
    assert data["mapped_channels_count"] == 1
    assert data["channels_with_programs"] == 1
    assert data["programs_count"] == 1
    assert data["days_count"] == 2.0
    assert data["start_date"] is not None
    assert data["end_date"] is not None


def test_reload_xmltv_success(admin_client, tmp_db, monkeypatch):
    save_network_integration("xmltv", "xmltv", "XMLTV", {"url": "http://example.com/feed.xml"})
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    
    xml_data = (
        "<tv>"
        '  <channel id="4.1">'
        "    <display-name>WNBC</display-name>"
        "  </channel>"
        '  <programme channel="4.1" start="20260822100000 +0000" stop="20260824100000 +0000">'
        "    <title>Today Show</title>"
        "  </programme>"
        "</tv>"
    )
    from xml.etree import ElementTree
    root = ElementTree.fromstring(xml_data)
    monkeypatch.setattr(guide_api.xmltv, "_fetch_xmltv_root", AsyncMock(return_value=root))

    response = admin_client.post("/api/guide/xmltv/reload")
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["message"] == "XMLTV guide reloaded successfully"
    stats = data["stats"]
    assert stats["channels_in_feed"] == 1
    assert stats["mapped_channels_count"] == 1
    assert stats["programs_count"] == 1
    assert stats["days_count"] == 2.0


def test_reload_xmltv_unconfigured(admin_client, tmp_db):
    response = admin_client.post("/api/guide/xmltv/reload")
    assert response.status_code == 400
    assert "not configured" in response.json()["detail"]


def test_reload_xmltv_fetch_failure(admin_client, tmp_db, monkeypatch):
    save_network_integration("xmltv", "xmltv", "XMLTV", {"url": "http://example.com/bad.xml"})
    monkeypatch.setattr(guide_api.xmltv, "_fetch_xmltv_root", AsyncMock(return_value=None))

    response = admin_client.post("/api/guide/xmltv/reload")
    assert response.status_code == 400
    assert "Could not fetch or parse" in response.json()["detail"]


def test_reload_xmltv_requires_admin(client, tmp_db):
    response = client.post("/api/guide/xmltv/reload")
    assert response.status_code == 403


def test_get_guide_includes_in_progress_and_recent_past_airings(client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()
    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "hdhomerun_cloud",
                "external_program_id": "SH100",
                "title": "In Progress Show",
                "episode_title": None,
                "season_number": None,
                "episode_number": None,
                "synopsis": None,
                "start_ts": now - 3600,
                "end_ts": now + 1800,
                "original_air_date": None,
                "image_url": None,
                "is_new": 0,
                "category": None,
            },
            {
                "channel_id": channel_id,
                "source_provider": "hdhomerun_cloud",
                "external_program_id": "SH101",
                "title": "Recently Ended Show",
                "episode_title": None,
                "season_number": None,
                "episode_number": None,
                "synopsis": None,
                "start_ts": now - 7200,
                "end_ts": now - 1800,
                "original_air_date": None,
                "image_url": None,
                "is_new": 0,
                "category": None,
            },
        ]
    )

    response = client.get("/api/guide")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    titles = [a["title"] for a in data[0]["airings"]]
    assert "In Progress Show" in titles
    assert "Recently Ended Show" in titles


def test_get_guide_auto_seeds_channels_from_tuner_if_empty(client, tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    tuner_channels = [
        {"channel_number": "5.1", "name": "WNYW", "is_hd": True, "is_drm": False, "stream_url": "http://x/5.1"}
    ]
    monkeypatch.setattr(guide_api.hdhomerun_client, "fetch_lineup", AsyncMock(return_value=tuner_channels))

    response = client.get("/api/guide")
    assert response.status_code == 200
    # Channel should now be in DB
    ch = db.get_channel_by_number("5.1")
    assert ch is not None
    assert ch["name"] == "WNYW"


def test_get_guide_start_end_params_filter_window(client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()
    db.upsert_guide_programs(
        [
            _program_row(channel_id, "hdhomerun_cloud", now, "In Window Show"),
            _program_row(channel_id, "hdhomerun_cloud", now + 10 * 24 * 3600, "Far Future Show"),
        ]
    )

    response = client.get("/api/guide", params={"start": now - 3600, "end": now + 3600})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    titles = [a["title"] for a in body[0]["airings"]]
    assert titles == ["In Window Show"]


def test_get_guide_omitted_params_use_default_window(client, tmp_db):
    """Regression guard: no start/end still reproduces the historical
    default window (now - 6h .. now + QUERY_WINDOW_SECONDS)."""
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()
    db.upsert_guide_programs(
        [
            _program_row(channel_id, "hdhomerun_cloud", now, "Today Show"),
            _program_row(channel_id, "hdhomerun_cloud", now + 13 * 24 * 3600, "Two Weeks Out Show"),
        ]
    )

    response = client.get("/api/guide")

    assert response.status_code == 200
    body = response.json()
    titles = [a["title"] for a in body[0]["airings"]]
    assert "Today Show" in titles
    assert "Two Weeks Out Show" in titles


def test_get_guide_caches_repeated_requests(client, tmp_db, monkeypatch):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()
    db.upsert_guide_programs([_program_row(channel_id, "hdhomerun_cloud", now, "Cached Show")])

    real_list_guide_programs = db.list_guide_programs
    call_count = 0

    def _counting_list_guide_programs(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return real_list_guide_programs(*args, **kwargs)

    monkeypatch.setattr(guide_api.db, "list_guide_programs", _counting_list_guide_programs)

    first = client.get("/api/guide", params={"start": now - 3600, "end": now + 3600})
    second = client.get("/api/guide", params={"start": now - 3600, "end": now + 3600})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert call_count == 1


def test_get_guide_refresh_invalidates_cache(client, tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()
    db.upsert_guide_programs([_program_row(channel_id, "hdhomerun_cloud", now, "Original Show")])

    first = client.get("/api/guide", params={"start": now - 3600, "end": now + 3600})
    assert [a["title"] for a in first.json()[0]["airings"]] == ["Original Show"]

    db.delete_future_guide_programs(channel_id, "hdhomerun_cloud", now - 4 * 3600)
    db.upsert_guide_programs([_program_row(channel_id, "hdhomerun_cloud", now, "Updated Show")])
    guide_api.cache.delete_prefix("guide:")

    second = client.get("/api/guide", params={"start": now - 3600, "end": now + 3600})
    assert [a["title"] for a in second.json()[0]["airings"]] == ["Updated Show"]



