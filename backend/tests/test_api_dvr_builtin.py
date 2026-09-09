from __future__ import annotations

import asyncio
import os
import time
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dvr as dvr_api
from app.api import dvr_streaming
from app.auth import get_current_user
from app.storage import db


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(dvr_api.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "role": "member"}
    return TestClient(app)


def test_get_dvr_info_builtin_fallback(client, tmp_db):
    response = client.get("/api/dvr/info")
    assert response.status_code == 200
    body = response.json()
    assert body["friendly_name"] == "HDHomeRun Open Built-in DVR"
    assert body["version"] == "1.0"
    assert body["is_builtin"] is True


def test_list_recordings_builtin(client, tmp_db):
    now = time.time()
    db.create_recording(
        {
            "id": "rec_test_1",
            "title": "Jeopardy!",
            "episode_title": "Game 1",
            "season_number": 40,
            "episode_number": 1,
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 1800,
            "file_path": "/tmp/rec_test_1.ts",
            "duration_seconds": 1800.0,
            "status": "completed",
            "synopsis": "Night 1 of Tournament.",
            "original_air_date": "2026-08-18",
            "category": "Game Show",
            "image_url": "http://example.com/j.jpg",
            "has_captions": 1,
            "video_codec": "h264",
            "video_width": 1920,
            "video_height": 1080,
            "audio_codec": "ac3",
            "audio_channels": 6,
            "file_size_bytes": 1048576,
        }
    )

    response = client.get("/api/dvr/recordings")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    rec = body[0]
    assert rec["recording_id"] == "rec_test_1"
    assert rec["title"] == "Jeopardy!"
    assert rec["episode_title"] == "Game 1"
    assert rec["episode_number"] == "40.1"
    assert rec["synopsis"] == "Night 1 of Tournament."
    assert rec["channel_number"] == "4.1"
    assert rec["is_dvr_file"] is True
    assert rec["has_captions"] is True
    assert rec["video_codec"] == "h264"
    assert rec["video_width"] == 1920
    assert rec["video_height"] == 1080
    assert rec["audio_codec"] == "ac3"
    assert rec["audio_channels"] == 6
    assert rec["file_size_bytes"] == 1048576
    assert rec["original_air_date"] == "2026-08-18"
    assert rec["category"] == "Game Show"


def test_get_recording_poster_fallback_and_generation(client, tmp_db, tmp_path, monkeypatch):
    dummy_ts = tmp_path / "test_rec.ts"
    dummy_ts.write_bytes(b"x" * 1000)

    dummy_jpg = tmp_path / "rec_poster.poster.jpg"
    dummy_jpg.write_bytes(b"JPEGDATA")

    from app.dvr.media import thumbnails
    monkeypatch.setattr(thumbnails, "generate_poster", AsyncMock(return_value=dummy_jpg))

    db.create_recording(
        {
            "id": "rec_poster",
            "title": "Movie Night",
            "channel_id": "5.1",
            "channel_name_snapshot": "KTLA",
            "start_ts": time.time() - 3600,
            "end_ts": time.time() - 1800,
            "file_path": str(dummy_ts),
            "status": "completed",
            "image_url": None,
        }
    )

    # Should fall back to poster endpoint URL when image_url is None
    rec_list = client.get("/api/dvr/recordings").json()
    assert rec_list[0]["image_url"] == "/api/dvr/recordings/rec_poster/poster.jpg"

    # Request the poster
    resp = client.get("/api/dvr/recordings/rec_poster/poster.jpg")
    assert resp.status_code == 200
    assert resp.content == b"JPEGDATA"


def test_create_and_delete_recording_rule_builtin(client, tmp_db, monkeypatch):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()
    airing_start = int(now + 3600)

    # Seed guide program
    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "hdhomerun_cloud",
                "external_program_id": "EP_JEOPARDY",
                "title": "Jeopardy!",
                "episode_title": "Episode 100",
                "season_number": 40,
                "episode_number": 100,
                "synopsis": "Trivia.",
                "start_ts": float(airing_start),
                "end_ts": float(airing_start + 1800),
                "original_air_date": "2026-08-18",
                "image_url": None,
                "is_new": 1,
                "category": None,
            }
        ]
    )

    # POST create series rule
    payload = {
        "series_id": "EP_JEOPARDY",
        "channel": "4.1",
        "recent_only": True,
        "start_padding": 60,
        "end_padding": 120,
        "max_episodes_to_keep": 3,
    }
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    rules = response.json()
    assert len(rules) == 1
    rule = rules[0]
    assert rule["Title"] == "Jeopardy!"
    assert rule["SeriesID"] == "EP_JEOPARDY"
    assert rule["ChannelOnly"] == "4.1"
    assert rule["StartPadding"] == 60
    assert rule["EndPadding"] == 120
    assert rule["RecentOnly"] == 1
    assert rule["MaxEpisodesToKeep"] == 3

    rule_id = rule["RecordingRuleID"]

    # GET recording-rules
    get_res = client.get("/api/dvr/recording-rules")
    assert get_res.status_code == 200
    assert len(get_res.json()) == 1

    # DELETE recording rule
    del_res = client.delete(f"/api/dvr/recording-rules/{rule_id}")
    assert del_res.status_code == 200
    assert len(del_res.json()) == 0
    assert db.get_recording_rule(rule_id) is None


def test_update_recording_rule_builtin(client, tmp_db):
    db.upsert_channel("ch_4_1", "4.1", "FOX 4", True)
    create_payload = {
        "series_id": "EP_NEWS",
        "channel": "4.1",
        "recent_only": False,
        "start_padding": 60,
        "end_padding": 120,
        "title": "Evening News",
    }
    create_res = client.post("/api/dvr/recording-rules", json=create_payload)
    assert create_res.status_code == 200
    rules = create_res.json()
    rule_id = rules[0]["RecordingRuleID"]

    update_payload = {
        "channel": "5.1",
        "recent_only": True,
        "start_padding": 300,
        "end_padding": 600,
        "max_episodes_to_keep": 5,
        "title_match_mode": "contains",
        "keyword_query": "breaking, special",
    }
    update_res = client.put(f"/api/dvr/recording-rules/{rule_id}", json=update_payload)
    assert update_res.status_code == 200
    updated_rules = update_res.json()
    assert len(updated_rules) == 1
    updated = updated_rules[0]
    assert updated["RecordingRuleID"] == rule_id
    assert updated["ChannelOnly"] == "5.1"
    assert updated["RecentOnly"] == 1
    assert updated["StartPadding"] == 300
    assert updated["EndPadding"] == 600
    assert updated["MaxEpisodesToKeep"] == 5
    assert updated["TitleMatchMode"] == "contains"
    assert updated["KeywordQuery"] == "breaking, special"

    db_rule = db.get_recording_rule(rule_id)
    assert db_rule is not None
    assert db_rule["channel_id"] == "5.1"
    assert db_rule["new_only"] == 1
    assert db_rule["start_padding_seconds"] == 300
    assert db_rule["end_padding_seconds"] == 600
    assert db_rule["max_episodes_to_keep"] == 5
    assert db_rule["title_match_mode"] == "contains"
    assert db_rule["keyword_query"] == "breaking, special"


def test_update_recording_rule_no_server_change_uses_in_place_update(client, tmp_db):
    db.upsert_channel("ch_4_1", "4.1", "FOX 4", True)
    create_payload = {"series_id": "EP_NEWS", "channel": "4.1", "title": "Evening News"}
    create_res = client.post("/api/dvr/recording-rules", json=create_payload)
    rule_id = create_res.json()[0]["RecordingRuleID"]

    # Explicit "builtin" while already builtin should take the in-place
    # update path (same id afterwards), not a needless migrate-and-recreate.
    response = client.put(f"/api/dvr/recording-rules/{rule_id}", json={"server": "builtin", "channel": "5.1"})
    assert response.status_code == 200

    db_rule = db.get_recording_rule(rule_id)
    assert db_rule is not None
    assert db_rule["id"] == rule_id
    assert db_rule["channel_id"] == "5.1"


def test_update_recording_rule_switches_builtin_to_hdhomerun(client, tmp_db, monkeypatch):
    from app.integrations import hdhomerun_client

    db.upsert_channel("ch_4_1", "4.1", "FOX 4", True)
    create_payload = {
        "series_id": "EP_NEWS",
        "channel": "4.1",
        "recent_only": False,
        "start_padding": 60,
        "end_padding": 120,
        "title": "Evening News",
    }
    create_res = client.post("/api/dvr/recording-rules", json=create_payload)
    rule_id = create_res.json()[0]["RecordingRuleID"]
    assert db.get_recording_rule(rule_id) is not None

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})
    mock_add = AsyncMock(return_value=[{"RecordingRuleID": "off_1", "SeriesID": "EP_NEWS", "Provider": "hdhomerun"}])
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    response = client.put(f"/api/dvr/recording-rules/{rule_id}", json={"server": "hdhomerun"})
    assert response.status_code == 200
    assert mock_add.called
    passed_rule_data = mock_add.call_args[0][1]
    assert passed_rule_data["series_id"] == "EP_NEWS"
    assert passed_rule_data["channel"] == "4.1"
    assert passed_rule_data["start_padding"] == 60
    assert passed_rule_data["end_padding"] == 120

    assert db.get_recording_rule(rule_id) is None
    assert all(sr["rule_id"] != rule_id for sr in db.list_scheduled_recordings())


def test_update_recording_rule_switches_hdhomerun_to_builtin(client, tmp_db, monkeypatch):
    from app.integrations import hdhomerun_client

    official_rule_id = "off_news_1"
    official_rule = {
        "RecordingRuleID": official_rule_id,
        "SeriesID": "EP_NEWS",
        "Title": "Evening News",
        "ChannelOnly": "4.1",
        "RecentOnly": 0,
        "StartPadding": 60,
        "EndPadding": 120,
    }
    monkeypatch.setattr(hdhomerun_client, "fetch_dvr_recording_rules", AsyncMock(return_value=[official_rule]))
    mock_delete = AsyncMock(return_value=[])
    monkeypatch.setattr(hdhomerun_client, "delete_recording_rule", mock_delete)

    response = client.put(f"/api/dvr/recording-rules/{official_rule_id}", json={"server": "builtin"})
    assert response.status_code == 200
    mock_delete.assert_called_once()
    assert mock_delete.call_args[0][1] == official_rule_id

    builtin_rules = db.list_recording_rules("builtin")
    assert len(builtin_rules) == 1
    new_rule = builtin_rules[0]
    assert new_rule["id"] != official_rule_id
    assert new_rule["title"] == "Evening News"
    assert new_rule["channel_id"] == "4.1"
    assert new_rule["start_padding_seconds"] == 60
    assert new_rule["end_padding_seconds"] == 120
    assert new_rule["series_match_key"] == "EP_NEWS"


def test_update_recording_rule_rejects_keyword_rule_switch_to_hdhomerun(client, tmp_db):
    payload = {"title": "College Football", "keyword_query": "Ohio State"}
    create_res = client.post("/api/dvr/recording-rules", json=payload)
    rule_id = create_res.json()[0]["RecordingRuleID"]

    response = client.put(f"/api/dvr/recording-rules/{rule_id}", json={"server": "hdhomerun"})
    assert response.status_code == 400
    assert "builtin" in response.json()["detail"].lower()

    db_rule = db.get_recording_rule(rule_id)
    assert db_rule is not None
    assert db_rule["provider"] == "builtin"
    assert db_rule["keyword_query"] == "Ohio State"


def test_update_recording_rule_switch_to_hdhomerun_fails_leaves_builtin_rule_intact(client, tmp_db, monkeypatch):
    from app.integrations import hdhomerun_client

    db.upsert_channel("ch_4_1", "4.1", "FOX 4", True)
    create_payload = {"series_id": "EP_NEWS", "channel": "4.1", "title": "Evening News"}
    create_res = client.post("/api/dvr/recording-rules", json=create_payload)
    rule_id = create_res.json()[0]["RecordingRuleID"]

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})
    add_error = hdhomerun_client.HDHomeRunError("Add recording rule failed (HTTP 400): Invalid SeriesID")
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", AsyncMock(side_effect=add_error))

    response = client.put(f"/api/dvr/recording-rules/{rule_id}", json={"server": "hdhomerun"})
    assert response.status_code == 400
    assert "Invalid SeriesID" in response.json()["detail"]

    db_rule = db.get_recording_rule(rule_id)
    assert db_rule is not None
    assert db_rule["id"] == rule_id


def test_create_recording_rule_max_episodes_to_keep_omitted(client, tmp_db):
    payload = {"series_id": "auto", "channel": "4.1"}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    rule = response.json()[0]
    assert rule["MaxEpisodesToKeep"] is None


def test_create_recording_rule_max_episodes_to_keep_rejects_zero(client, tmp_db):
    payload = {"series_id": "auto", "channel": "4.1", "max_episodes_to_keep": 0}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 422


def test_delete_recording_builtin(client, tmp_db, tmp_path, monkeypatch):
    from app.dvr.builtin import retention

    monkeypatch.setattr(retention, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(retention, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path / "cache")

    video_file = tmp_path / "test_del.ts"
    video_file.write_bytes(b"DATA")

    db.create_recording(
        {
            "id": "rec_to_delete",
            "title": "Old Episode",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    del_res = client.delete("/api/dvr/recordings/rec_to_delete")
    assert del_res.status_code == 200
    assert del_res.json() == {"status": "deleted"}
    assert not video_file.exists()
    assert db.get_recording("rec_to_delete") is None


def test_delete_recording_invalidates_probe_and_edl_cache(client, tmp_db, tmp_path, monkeypatch):
    from app.dvr.builtin import retention

    monkeypatch.setattr(retention, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(retention, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path / "cache")

    video_file = tmp_path / "test_del_cache.ts"
    video_file.write_bytes(b"DATA")

    db.create_recording(
        {
            "id": "rec_cached",
            "title": "Cached Episode",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    dvr_streaming._probe_cache["rec_cached"] = {"duration": 1234.0}
    dvr_streaming._probe_cache_in_progress["rec_cached"] = {}
    dvr_streaming._edl_cache["rec_cached"] = (0.0, [])

    del_res = client.delete("/api/dvr/recordings/rec_cached")
    assert del_res.status_code == 200

    assert "rec_cached" not in dvr_streaming._probe_cache
    assert "rec_cached" not in dvr_streaming._probe_cache_in_progress
    assert "rec_cached" not in dvr_streaming._edl_cache


def test_delete_recording_not_found(client, tmp_db):
    res = client.delete("/api/dvr/recordings/non_existent_rec")
    assert res.status_code == 404


def test_delete_recording_rejects_in_progress(client, tmp_db, tmp_path, monkeypatch):
    from app.dvr.builtin import retention
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    monkeypatch.setattr(retention, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(retention, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path / "cache")

    video_file = tmp_path / "rec_live.ts"
    video_file.write_bytes(b"DATA")

    db.create_recording(
        {
            "id": "rec_live",
            "title": "Live Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "recording",
        }
    )

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_live",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 60,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_live"] = active_capture

    try:
        res = client.delete("/api/dvr/recordings/rec_live")
        assert res.status_code == 409
        assert video_file.exists()
        assert db.get_recording("rec_live") is not None
    finally:
        capture_pipeline._active_captures.pop("rec_live", None)


def test_create_recording_rule_respects_dvr_server_priority(client, tmp_db, monkeypatch):
    from app.integrations import hdhomerun_client

    db.save_app_settings({"dvr_server_priority": "hdhomerun,builtin"})
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})

    mock_add = AsyncMock(return_value=[{"RecordingRuleID": "off_1", "SeriesID": "auto", "Provider": "hdhomerun"}])
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    payload = {"series_id": "auto", "channel": "4.1"}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    assert mock_add.called


def test_create_recording_rule_explicit_server_override(client, tmp_db, monkeypatch):
    from app.integrations import hdhomerun_client

    # Default priority is hdhomerun, but request specifies server="builtin"
    db.save_app_settings({"dvr_server_priority": "hdhomerun,builtin"})
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})

    mock_add = AsyncMock(return_value=[])
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    payload = {"series_id": "auto", "channel": "4.1", "server": "builtin"}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    # Official DVR add should NOT have been called
    assert not mock_add.called
    rules = response.json()
    assert len(rules) == 1
    assert rules[0]["provider"] == "builtin"


def test_create_recording_rule_explicit_hdhomerun_unconfigured_fails(client, tmp_db):
    payload = {"series_id": "auto", "channel": "4.1", "server": "hdhomerun"}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 400
    assert "not configured" in response.json()["detail"]


def test_create_recording_rule_hdhomerun_fallback_when_series_id_missing(client, tmp_db):

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})

    payload = {"series_id": "auto", "channel": "4.1", "server": "hdhomerun", "title": "Local News"}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    assert response.headers.get("X-DVR-Fallback") == "true"
    assert response.headers.get("X-DVR-Fallback-Reason") == "guide_series_id_missing"

    rules = response.json()
    assert len(rules) == 1
    assert rules[0]["provider"] == "builtin"
    assert rules[0]["fallback_reason"] == "guide_series_id_missing"
    assert rules[0]["FallbackReason"] == "guide_series_id_missing"


def test_create_recording_rule_hdhomerun_auto_resolves_series_id_from_cloud_guide(client, tmp_db, monkeypatch):
    from app.integrations import hdhomerun_client

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})
    db.upsert_channel("ch_41", "4.1", "KTVK", True)
    db.upsert_guide_programs(
        [
            {
                "id": "prog_jeop",
                "channel_id": "ch_41",
                "source_provider": "hdhomerun_cloud",
                "external_program_id": "EP_JEOP_999",
                "title": "Jeopardy!",
                "episode_title": "Tournament",
                "start_ts": 1725465600,
                "end_ts": 1725467400,
            }
        ]
    )

    mock_add = AsyncMock(return_value=[{"RecordingRuleID": "rule_off_jeop", "SeriesID": "EP_JEOP_999", "Provider": "hdhomerun"}])
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    payload = {
        "series_id": "auto",
        "channel": "4.1",
        "date_time": 1725465600,
        "title": "Jeopardy!",
        "server": "hdhomerun",
    }
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    assert mock_add.called
    passed_rule_data = mock_add.call_args[0][1]
    assert passed_rule_data["series_id"] == "EP_JEOP_999"


def test_create_recording_rule_hdhomerun_fallback_on_client_error(client, tmp_db, monkeypatch):
    from app.integrations import hdhomerun_client

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})

    mock_add = AsyncMock(side_effect=hdhomerun_client.HDHomeRunError("Add recording rule failed (HTTP 400): Airing not found"))
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    payload = {
        "series_id": "EP123",
        "channel": "4.1",
        "server": "hdhomerun",
        "title": "Problematic Show",
    }
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    assert response.headers.get("X-DVR-Fallback") == "true"

    rules = response.json()
    assert len(rules) == 1
    assert rules[0]["provider"] == "builtin"
    assert "Airing not found" in rules[0]["fallback_reason"]



def test_create_keyword_recording_rule_with_no_series_id_or_date_time(client, tmp_db):
    payload = {
        "title": "College Football",
        "title_match_mode": "exact",
        "keyword_query": "Ohio State",
    }
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    rules = response.json()
    assert len(rules) == 1
    rule = rules[0]
    assert rule["Title"] == "College Football"
    assert rule["TitleMatchMode"] == "exact"
    assert rule["KeywordQuery"] == "Ohio State"
    assert rule["provider"] == "builtin"

    # Round-trip via GET
    get_res = client.get("/api/dvr/recording-rules")
    assert get_res.status_code == 200
    fetched = get_res.json()[0]
    assert fetched["TitleMatchMode"] == "exact"
    assert fetched["KeywordQuery"] == "Ohio State"


def test_create_keyword_recording_rule_rejects_explicit_hdhomerun_server(client, tmp_db):
    payload = {
        "title": "College Football",
        "keyword_query": "Ohio State",
        "server": "hdhomerun",
    }
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 400
    assert "builtin" in response.json()["detail"].lower()


def test_create_contains_mode_recording_rule_rejects_explicit_hdhomerun_server(client, tmp_db):
    payload = {
        "title": "College Football",
        "title_match_mode": "contains",
        "server": "hdhomerun",
    }
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 400
    assert "builtin" in response.json()["detail"].lower()


def test_create_keyword_recording_rule_falls_through_to_builtin_despite_hdhomerun_priority(
    client, tmp_db, monkeypatch
):
    from app.integrations import hdhomerun_client

    db.save_app_settings({"dvr_server_priority": "hdhomerun,builtin"})
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_port": 50000})

    mock_add = AsyncMock(return_value=[])
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    payload = {"title": "College Football", "keyword_query": "Ohio State"}
    response = client.post("/api/dvr/recording-rules", json=payload)
    assert response.status_code == 200
    assert not mock_add.called
    rules = response.json()
    assert len(rules) == 1
    assert rules[0]["provider"] == "builtin"


def test_recording_detail_probes_in_progress_recording_once_enough_data(client, tmp_db, tmp_path, monkeypatch):
    """An in-progress recording should surface real video/audio metadata
    (needed for the live audio-track/SAP menu and the playback-info panel)
    once media_probe.probe_in_progress finds enough data on disk, instead of
    the old hardcoded empty stub."""
    from app import media_probe as media_probe_module

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "in_progress.ts"
    video_file.write_bytes(b"MPEG-TS data" * 10000)

    now = time.time()
    db.create_recording(
        {
            "id": "rec_live",
            "title": "Live Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 60,
            "end_ts": now + 600,
            "file_path": str(video_file),
            "status": "recording",
        }
    )

    probe_result = {
        "video": {"codec": "mpeg2video", "width": 1280, "height": 720, "fps": 59.94},
        "audio": [{"index": 0, "codec": "ac3", "channels": 6, "language": "eng"}],
        "has_captions": True,
    }
    mock_probe = AsyncMock(return_value=probe_result)
    monkeypatch.setattr(media_probe_module, "probe_in_progress", mock_probe)

    response = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_live", "start": now - 60},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_in_progress"] is True
    assert body["video"] == probe_result["video"]
    assert body["audio"] == probe_result["audio"]
    assert body["has_captions"] is True
    mock_probe.assert_awaited_once()

    # A second poll while still in-progress reuses the cached result rather
    # than probing again.
    response2 = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_live", "start": now - 60},
    )
    assert response2.status_code == 200
    assert response2.json()["video"] == probe_result["video"]
    mock_probe.assert_awaited_once()


def test_recording_detail_surfaces_transcode_preset_for_completed_recording(client, tmp_db, tmp_path):
    """The playback-info panel needs to know whether the server transcodes
    at all, and if so via which preset, to show "Direct passthrough" vs
    "Transcoding via {preset_label}"."""
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local", "hwaccel": "software"}
    )

    video_file = tmp_path / "done.ts"
    video_file.write_bytes(b"MPEG-TS data")

    db.create_recording(
        {
            "id": "rec_done",
            "title": "Finished Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    response = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_done", "start": 1000.0, "record_end": 2000.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_in_progress"] is False
    assert body["transcode"] == {
        "transcoding": True,
        "preset": "software",
        "preset_label": "Software (libx264)",
        "hardware": False,
    }


def test_recording_detail_surfaces_direct_passthrough_when_transcoding_disabled(client, tmp_db, tmp_path):
    # Even with playback_mode="external" (direct passthrough for
    # /recording-stream), preset/hardware are still resolved: native clients'
    # /recording-stream-hls path always transcodes regardless of this
    # setting, so they need real preset info even when "transcoding" is False.
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local", "playback_mode": "external"}
    )

    video_file = tmp_path / "in_progress.ts"
    video_file.write_bytes(b"MPEG-TS data")

    now = time.time()
    db.create_recording(
        {
            "id": "rec_live_passthrough",
            "title": "Live Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 60,
            "end_ts": now + 600,
            "file_path": str(video_file),
            "status": "recording",
        }
    )

    response = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_live_passthrough", "start": now - 60},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_in_progress"] is True
    assert body["transcode"] == {
        "transcoding": False,
        "preset": "software",
        "preset_label": "Software (libx264)",
        "hardware": False,
    }


def test_recording_detail_surfaces_commercial_segments_from_edl_sidecar(client, tmp_db, tmp_path):
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "with_edl.ts"
    video_file.write_bytes(b"MPEG-TS data")
    edl_file = video_file.with_suffix(".edl")
    edl_file.write_text("10 20 0\n50 65 0\n")

    db.create_recording(
        {
            "id": "rec_with_edl",
            "title": "Finished Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    response = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_with_edl", "start": 1000.0, "record_end": 2000.0},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["commercial_segments"] == [
        {"start_seconds": 10.0, "end_seconds": 20.0},
        {"start_seconds": 50.0, "end_seconds": 65.0},
    ]


def test_recording_detail_commercial_segments_empty_without_edl_sidecar(client, tmp_db, tmp_path):
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "no_edl.ts"
    video_file.write_bytes(b"MPEG-TS data")

    db.create_recording(
        {
            "id": "rec_no_edl",
            "title": "Finished Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    response = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_no_edl", "start": 1000.0, "record_end": 2000.0},
    )
    assert response.status_code == 200
    assert response.json()["commercial_segments"] == []


def test_recording_detail_commercial_segments_empty_for_in_progress_without_filesystem_access(
    client, tmp_db, tmp_path, monkeypatch
):
    from app.dvr import edl_parser as edl_parser_module

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "in_progress_edl.ts"
    video_file.write_bytes(b"MPEG-TS data" * 10000)

    now = time.time()
    db.create_recording(
        {
            "id": "rec_live_edl",
            "title": "Live Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 60,
            "end_ts": now + 600,
            "file_path": str(video_file),
            "status": "recording",
        }
    )

    mock_parse = MagicMock(side_effect=AssertionError("comskip parsing must not run for in-progress recordings"))
    monkeypatch.setattr(edl_parser_module, "parse_edl_file", mock_parse)

    response = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_live_edl", "start": now - 60},
    )
    assert response.status_code == 200
    assert response.json()["commercial_segments"] == []
    mock_parse.assert_not_called()


def test_recording_detail_commercial_segments_invalidate_on_edl_mtime_change(client, tmp_db, tmp_path):
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "growing_edl.ts"
    video_file.write_bytes(b"MPEG-TS data")
    edl_file = video_file.with_suffix(".edl")
    edl_file.write_text("10 20 0\n")

    db.create_recording(
        {
            "id": "rec_growing_edl",
            "title": "Finished Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    params = {"url": str(video_file), "recording_id": "rec_growing_edl", "start": 1000.0, "record_end": 2000.0}

    first = client.get("/api/dvr/recording-detail", params=params)
    assert first.json()["commercial_segments"] == [{"start_seconds": 10.0, "end_seconds": 20.0}]

    # comskip finishes writing a fuller cutlist sometime after the recording
    # completed and was first probed; bump the mtime so the cache notices.
    edl_file.write_text("10 20 0\n30 45 0\n")
    new_mtime = edl_file.stat().st_mtime + 5
    os.utime(edl_file, (new_mtime, new_mtime))

    second = client.get("/api/dvr/recording-detail", params=params)
    assert second.json()["commercial_segments"] == [
        {"start_seconds": 10.0, "end_seconds": 20.0},
        {"start_seconds": 30.0, "end_seconds": 45.0},
    ]


def test_recording_captions_serves_live_vtt_for_in_progress_recording(client, tmp_db, tmp_path, monkeypatch):
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline
    from app.dvr.media import captions_live

    video_file = tmp_path / "in_progress.ts"
    video_file.write_bytes(b"MPEG-TS data")

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_live",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 60,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_live"] = active_capture

    def fake_ensure_live_captions(recording_id, file_path, is_source_alive, capture_start_ts=None, channel=1):
        captions_live.live_captions_path(recording_id, channel).write_text(
            "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHi\n"
        )

    monkeypatch.setattr(captions_live, "ensure_live_captions", fake_ensure_live_captions)

    try:
        response = client.get(
            "/api/dvr/recording-captions.vtt",
            params={"url": str(video_file), "recording_id": "rec_live", "record_end": now + 600},
        )
        assert response.status_code == 200
        assert "Hi" in response.text
    finally:
        capture_pipeline._active_captures.pop("rec_live", None)
        captions_live.live_captions_path("rec_live").unlink(missing_ok=True)


def test_recording_captions_404_when_capture_gone(client, tmp_db, tmp_path):
    response = client.get(
        "/api/dvr/recording-captions.vtt",
        params={"url": str(tmp_path / "gone.ts"), "recording_id": "rec_gone", "record_end": time.time() + 600},
    )
    assert response.status_code == 404


def test_recording_captions_track2_routes_to_channel2_path(client, tmp_db, tmp_path, monkeypatch):
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline
    from app.dvr.media import captions_live

    video_file = tmp_path / "in_progress.ts"
    video_file.write_bytes(b"MPEG-TS data")

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_live",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 60,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_live"] = active_capture

    received_channels: list[int] = []

    def fake_ensure_live_captions(recording_id, file_path, is_source_alive, capture_start_ts=None, channel=1):
        received_channels.append(channel)
        captions_live.live_captions_path(recording_id, channel).write_text(
            "WEBVTT\n\n00:00:05.000 --> 00:00:06.000\nSegunda\n"
        )

    monkeypatch.setattr(captions_live, "ensure_live_captions", fake_ensure_live_captions)

    try:
        response = client.get(
            "/api/dvr/recording-captions.vtt",
            params={"url": str(video_file), "recording_id": "rec_live", "record_end": now + 600, "track": 2},
        )
        assert response.status_code == 200
        assert "Segunda" in response.text
        assert received_channels == [2]
    finally:
        capture_pipeline._active_captures.pop("rec_live", None)
        captions_live.live_captions_path("rec_live", channel=2).unlink(missing_ok=True)


def test_recording_captions_invalid_track_returns_400(client, tmp_db, tmp_path):
    response = client.get(
        "/api/dvr/recording-captions.vtt",
        params={
            "url": str(tmp_path / "whatever.ts"),
            "recording_id": "rec_x",
            "record_end": time.time() + 600,
            "track": 3,
        },
    )
    assert response.status_code == 400


def test_recording_captions_track2_404_for_finished_recording(client, tmp_db, tmp_path):
    video_file = tmp_path / "done.ts"
    video_file.write_bytes(b"MPEG-TS data")

    response = client.get(
        "/api/dvr/recording-captions.vtt",
        params={
            "url": str(video_file),
            "recording_id": "rec_done",
            "record_end": time.time() - 10,
            "track": 2,
        },
    )
    assert response.status_code == 404


def test_recording_detail_secondary_captions_reflects_track2_status(client, tmp_db, tmp_path, monkeypatch):
    from app import media_probe as media_probe_module
    from app.dvr.media import captions_live

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "in_progress.ts"
    video_file.write_bytes(b"MPEG-TS data" * 10000)

    now = time.time()
    probe_result = {"video": None, "audio": [], "has_captions": False}
    monkeypatch.setattr(media_probe_module, "probe_in_progress", AsyncMock(return_value=probe_result))
    monkeypatch.setattr(captions_live, "live_caption_track2_status", lambda recording_id: "unknown")

    response = client.get(
        "/api/dvr/recording-detail",
        params={"url": str(video_file), "recording_id": "rec_live_secondary", "start": now - 60},
    )
    assert response.status_code == 200
    assert response.json()["secondary_captions"] == "unknown"

    # Finished recordings never report a secondary track, regardless of
    # captions_live state - only live recordings run the channel-2 pipeline.
    db.create_recording(
        {
            "id": "rec_done_secondary",
            "title": "Finished Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
            "file_path": str(video_file),
            "status": "completed",
        }
    )
    response2 = client.get(
        "/api/dvr/recording-detail",
        params={
            "url": str(video_file),
            "recording_id": "rec_done_secondary",
            "start": 1000.0,
            "record_end": 2000.0,
        },
    )
    assert response2.status_code == 200
    assert response2.json()["secondary_captions"] is None


def _fake_transcode_process() -> MagicMock:
    proc = MagicMock()
    proc.returncode = None
    proc.terminate = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    proc.stdin = MagicMock()
    proc.stdin.write = MagicMock()
    proc.stdin.drain = AsyncMock()
    proc.stdin.close = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.read = AsyncMock(side_effect=[b"chunk", b""])
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(return_value=b"")
    return proc


def test_recording_stream_proceeds_immediately_once_capture_has_data(client, tmp_db, tmp_path, monkeypatch):
    """A viewer attaching to a capture that's already been writing for a
    while (the common case) shouldn't be slowed down at all by the new
    pre-flight readiness check - the file is already well past the ready
    threshold, so it should pass on the very first check."""
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "live.ts"
    video_file.write_bytes(b"x" * (dvr_streaming._LIVE_CAPTURE_READY_MIN_BYTES + 1))

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_ready",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 60,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_ready"] = active_capture

    spawn_mock = AsyncMock(side_effect=lambda *a, **kw: _fake_transcode_process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_mock)

    try:
        response = client.get(
            "/api/dvr/recording-stream",
            params={"url": str(video_file), "recording_id": "rec_ready"},
        )
        assert response.status_code == 200
    finally:
        capture_pipeline._active_captures.pop("rec_ready", None)


@pytest.mark.asyncio
async def test_recording_stream_spawn_failure_502s_stops_pump_and_skips_hwaccel_probe(tmp_db, tmp_path, monkeypatch):
    """Reproduces a tail-follow (live) recording-stream whose downstream
    transcode ffmpeg fails to produce any output: the 502 detail should carry
    the real ffmpeg-stderr-derived reason, the tail-follow pump feeding that
    ffmpeg's stdin must be torn down (stop_pump), and - since this is the
    recording-stream path, not live-channel streaming - the hwaccel
    diagnostic probe must never run (see the 3d scope decision: recording
    failures aren't hardware-preset-enriched).

    Calls the route function directly rather than through TestClient: the
    background tasks under test (drain/terminate/stop_pump, all fired via
    run_in_background) need to be awaited deterministically afterward, which
    only works reliably when they're scheduled on this test's own event
    loop rather than on TestClient's separate portal loop/thread.
    """
    from fastapi import HTTPException

    from app import hwaccel
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "live_failing.ts"
    video_file.write_bytes(b"x" * (dvr_streaming._LIVE_CAPTURE_READY_MIN_BYTES + 1))

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_spawn_fail",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 60,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_spawn_fail"] = active_capture

    proc = MagicMock()
    proc.returncode = 1
    proc.terminate = MagicMock()
    proc.wait = AsyncMock(return_value=1)
    proc.stdin = MagicMock()
    proc.stdin.close = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.read = AsyncMock(return_value=b"")
    proc.stderr = MagicMock()
    proc.stderr.read = AsyncMock(side_effect=[b"downstream ffmpeg exploded", b""])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=proc))

    async def fake_pump_tail_follow(file_path, writer, stop_event, is_alive, *, start_offset_bytes=None):
        await stop_event.wait()

    monkeypatch.setattr(dvr_streaming, "pump_tail_follow", fake_pump_tail_follow)

    background_tasks: list[asyncio.Task] = []

    def tracking_run_in_background(coro):
        task = asyncio.ensure_future(coro)
        background_tasks.append(task)
        return task

    monkeypatch.setattr(dvr_streaming, "run_in_background", tracking_run_in_background)

    mock_probe = AsyncMock()
    monkeypatch.setattr(hwaccel, "probe_transcode", mock_probe)

    try:
        fake_request = SimpleNamespace(url=f"/api/dvr/recording-stream?url={video_file}&recording_id=rec_spawn_fail")
        with pytest.raises(HTTPException) as exc_info:
            await dvr_streaming.stream_recording(
                fake_request, url=str(video_file), recording_id="rec_spawn_fail"
            )

        assert exc_info.value.status_code == 502
        detail = exc_info.value.detail
        assert "Could not start streaming recording" in detail
        assert "downstream ffmpeg exploded" in detail

        assert len(background_tasks) == 3  # drain_stderr_tail, terminate_process, stop_pump
        await asyncio.gather(*background_tasks)

        assert proc.stdin.close.called, "stop_pump should have closed the transcode ffmpeg's stdin"
        mock_probe.assert_not_awaited()
    finally:
        capture_pipeline._active_captures.pop("rec_spawn_fail", None)


def test_recording_stream_502s_without_spawning_ffmpeg_when_capture_stays_empty(client, tmp_db, tmp_path, monkeypatch):
    """Reproduces the real-world race: a viewer requests a stream for a
    recording_id whose capture was just registered (see
    CapturePipeline.start_capture, which adds the ActiveCapture the instant
    the writer ffmpeg is spawned - before it has locked the tuner or written
    a single byte). The pre-flight wait should time out and fail fast with a
    clear cause, and - critically - should never spawn the downstream
    transcode ffmpeg at all, since there's nothing yet for it to read."""
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "just_started.ts"
    video_file.write_bytes(b"")  # writer hasn't flushed anything yet

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_empty",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_empty"] = active_capture

    monkeypatch.setattr(dvr_streaming, "_LIVE_CAPTURE_READY_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(dvr_streaming, "_LIVE_CAPTURE_READY_POLL_SECONDS", 0.01)
    spawn_mock = AsyncMock(side_effect=lambda *a, **kw: _fake_transcode_process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_mock)

    try:
        response = client.get(
            "/api/dvr/recording-stream",
            params={"url": str(video_file), "recording_id": "rec_empty"},
        )
        assert response.status_code == 502
        assert "tuner did not produce any data" in response.json()["detail"]
        spawn_mock.assert_not_awaited()
    finally:
        capture_pipeline._active_captures.pop("rec_empty", None)


def test_recording_stream_repeat_request_after_502_fails_fast_without_respawning(
    client, tmp_db, tmp_path, monkeypatch
):
    """The web player re-requests the exact same URL right after a failed
    stream to read the 502 detail its player library discarded (see
    frontend/src/lib/mpegts-player.ts). That only works as intended if the
    repeat request doesn't redo the slow tuner-readiness wait. Proven here by
    removing the ActiveCapture between the two requests - without the cache,
    the second request would take a completely different code path (and
    would spawn the transcode ffmpeg) instead of reproducing the same 502."""
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "just_started.ts"
    video_file.write_bytes(b"")

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_empty",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_empty"] = active_capture

    monkeypatch.setattr(dvr_streaming, "_LIVE_CAPTURE_READY_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(dvr_streaming, "_LIVE_CAPTURE_READY_POLL_SECONDS", 0.01)
    spawn_mock = AsyncMock(side_effect=lambda *a, **kw: _fake_transcode_process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_mock)

    try:
        params = {"url": str(video_file), "recording_id": "rec_empty"}
        first = client.get("/api/dvr/recording-stream", params=params)
        assert first.status_code == 502

        capture_pipeline._active_captures.pop("rec_empty", None)

        second = client.get("/api/dvr/recording-stream", params=params)
        assert second.status_code == 502
        assert second.json()["detail"] == first.json()["detail"]
        spawn_mock.assert_not_awaited()
    finally:
        capture_pipeline._active_captures.pop("rec_empty", None)


def test_recording_stream_waits_for_readiness_when_capture_file_not_yet_created(client, tmp_db, tmp_path, monkeypatch):
    """Reproduces the live-TV-from-the-guide regression: start_watch registers
    the ActiveCapture and DB row (see CapturePipeline.start_capture) before
    the writer ffmpeg has even created the file on disk - not merely before
    it's flushed any bytes. _resolve_target_media_url must not treat a
    not-yet-created file on an active capture as a deleted recording; it
    should fall through to the normal readiness wait and time out with the
    usual "tuner did not produce any data" 502, not an immediate 404."""
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "not_created_yet.ts"  # writer hasn't even created this file yet

    now = time.time()
    db.create_recording(
        {
            "id": "rec_not_created",
            "title": "Live Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now,
            "end_ts": now + 600,
            "file_path": str(video_file),
            "status": "recording",
        }
    )
    active_capture = ActiveCapture(
        recording_id="rec_not_created",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_not_created"] = active_capture

    monkeypatch.setattr(dvr_streaming, "_LIVE_CAPTURE_READY_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(dvr_streaming, "_LIVE_CAPTURE_READY_POLL_SECONDS", 0.01)
    spawn_mock = AsyncMock(side_effect=lambda *a, **kw: _fake_transcode_process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_mock)

    try:
        response = client.get(
            "/api/dvr/recording-stream",
            params={"url": str(video_file), "recording_id": "rec_not_created"},
        )
        assert response.status_code == 502
        assert "tuner did not produce any data" in response.json()["detail"]
        spawn_mock.assert_not_awaited()
    finally:
        capture_pipeline._active_captures.pop("rec_not_created", None)


def test_recording_stream_404s_when_inactive_recording_file_missing(client, tmp_db, tmp_path):
    """A completed (non-active) recording whose file has been deleted off
    disk should still get the clear 404, not the live-capture pass-through -
    guards the original fix this regression test's siblings were narrowing."""
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "deleted.ts"  # never created

    now = time.time()
    db.create_recording(
        {
            "id": "rec_deleted",
            "title": "Old Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 3000,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    response = client.get(
        "/api/dvr/recording-stream",
        params={"url": str(video_file), "recording_id": "rec_deleted"},
    )
    assert response.status_code == 404
    assert "no longer exists on disk" in response.json()["detail"]


def test_resolve_target_media_url_404s_for_unknown_recording_id_without_official_dvr(tmp_db):
    """A recording_id with no matching builtin-DVR row (deleted, stale client
    cache, or bogus) must not be treated as an official HDHomeRun DVR
    recording id when no official DVR is even configured - that used to fall
    through to hdhomerun_client.resolve_recording_url and build a URL against
    the tuner host on dvr_port's default (50000), producing an opaque 404
    from a device that was never the intended target."""
    from fastapi import HTTPException

    settings = {"tuner_host": "hdhomerun.local"}  # tuner only, no dvr_host
    with pytest.raises(HTTPException) as exc_info:
        dvr_streaming._resolve_target_media_url(settings, "/recorded/rec_missing", "rec_missing")
    assert exc_info.value.status_code == 404


def test_resolve_target_media_url_still_falls_through_when_official_dvr_configured(tmp_db, monkeypatch):
    """The same 'no local row' case must still resolve normally against the
    official HDHomeRun DVR when one is actually configured - this really is
    an official-DVR recording id, not a builtin one, and this path must not
    regress."""
    settings = {"tuner_host": "hdhomerun.local", "dvr_host": "dvr.local", "dvr_port": 50000}
    mock_resolve = MagicMock(return_value="http://dvr.local:50000/recorded/off_1")
    monkeypatch.setattr(dvr_api.hdhomerun_client, "resolve_recording_url", mock_resolve)

    result = dvr_streaming._resolve_target_media_url(settings, "/recorded/off_1", "off_1")

    assert result == "http://dvr.local:50000/recorded/off_1"
    mock_resolve.assert_called_once_with(settings, "/recorded/off_1")


def test_resolve_target_media_url_404s_for_builtin_provider_even_with_official_dvr_configured(
    tmp_db, monkeypatch
):
    """A client-tagged builtin recording whose row is missing locally (e.g. a
    stale client cache) must 404 with a clear local error - never fall
    through to the official DVR - even when one is configured. Regression
    test for the reported bug: a builtin recording was silently routed to
    the HDHomeRun DVR server (a 404 from port 50000) because the old
    fallthrough was only gated on whether an official DVR was configured at
    all, not on which server the recording actually belonged to."""
    from fastapi import HTTPException

    settings = {"tuner_host": "hdhomerun.local", "dvr_host": "dvr.local", "dvr_port": 50000}
    mock_resolve = MagicMock(return_value="http://dvr.local:50000/recorded/rec_missing")
    monkeypatch.setattr(dvr_api.hdhomerun_client, "resolve_recording_url", mock_resolve)

    with pytest.raises(HTTPException) as exc_info:
        dvr_streaming._resolve_target_media_url(
            settings, "/recorded/rec_missing", "rec_missing", provider="builtin"
        )

    assert exc_info.value.status_code == 404
    mock_resolve.assert_not_called()


def test_resolve_target_media_url_falls_through_for_hdhomerun_provider(tmp_db, monkeypatch):
    """A client-tagged official-DVR recording must resolve against the
    official DVR as normal."""
    settings = {"tuner_host": "hdhomerun.local", "dvr_host": "dvr.local", "dvr_port": 50000}
    mock_resolve = MagicMock(return_value="http://dvr.local:50000/recorded/off_1")
    monkeypatch.setattr(dvr_api.hdhomerun_client, "resolve_recording_url", mock_resolve)

    result = dvr_streaming._resolve_target_media_url(
        settings, "/recorded/off_1", "off_1", provider="hdhomerun"
    )

    assert result == "http://dvr.local:50000/recorded/off_1"
    mock_resolve.assert_called_once_with(settings, "/recorded/off_1")


def _spy_on_build_ffmpeg_args(monkeypatch, captured_kwargs: dict):
    real_build = dvr_streaming.transcoding.build_ffmpeg_args

    def _spy(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(dvr_streaming.transcoding, "build_ffmpeg_args", _spy)


def test_recording_stream_hls_uses_vod_packaging_for_completed_recording(client, tmp_db, tmp_path, monkeypatch):
    """A finished recording (no active capture) must be packaged with a real
    VOD playlist covering the whole file - not the live-style rolling window
    - so AVPlayer can scrub past the first ~24s. See transcoding.HLS_FLAGS_VOD."""
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "finished.ts"
    video_file.write_bytes(b"x" * 1024)

    now = time.time()
    db.create_recording(
        {
            "id": "rec_finished",
            "title": "Finished Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 3000,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    captured_kwargs: dict = {}
    _spy_on_build_ffmpeg_args(monkeypatch, captured_kwargs)

    fake_session = MagicMock()
    fake_session.session_id = "sess_vod"
    monkeypatch.setattr(dvr_streaming.hls_streaming, "create_session", AsyncMock(return_value=fake_session))

    response = client.post(
        "/api/dvr/recording-stream-hls",
        json={"url": str(video_file), "recording_id": "rec_finished"},
    )
    assert response.status_code == 200
    assert captured_kwargs["hls_vod"] is True


def test_recording_stream_hls_uses_live_style_packaging_for_active_capture(client, tmp_db, tmp_path, monkeypatch):
    """An in-progress recording/live watch (an active capture exists) must
    keep the existing rolling live-style HLS window - only a completed
    recording gets VOD packaging (regression guard for Fix 1)."""
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "live.ts"
    video_file.write_bytes(b"x" * (dvr_streaming._LIVE_CAPTURE_READY_MIN_BYTES + 1))

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_live_hls",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 60,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_live_hls"] = active_capture

    captured_kwargs: dict = {}
    _spy_on_build_ffmpeg_args(monkeypatch, captured_kwargs)

    fake_session = MagicMock()
    fake_session.session_id = "sess_live"

    async def _fake_create_session(*args, **kwargs):
        on_process_spawned = kwargs["on_process_spawned"]
        on_process_spawned(_fake_transcode_process())
        return fake_session

    monkeypatch.setattr(dvr_streaming.hls_streaming, "create_session", _fake_create_session)
    monkeypatch.setattr(dvr_streaming, "pump_tail_follow", AsyncMock(return_value=None))

    try:
        response = client.post(
            "/api/dvr/recording-stream-hls",
            json={"url": str(video_file), "recording_id": "rec_live_hls"},
        )
        assert response.status_code == 200
        assert captured_kwargs["hls_vod"] is False
    finally:
        capture_pipeline._active_captures.pop("rec_live_hls", None)


def test_recording_stream_hls_for_cast_returns_token_scoped_playlist_url(client, tmp_db, tmp_path, monkeypatch):
    """A Google Cast sender passes for_cast=true on the DVR HLS entry point
    too - same cast-token scoping as api/streaming.py's stream_channel_hls."""
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "finished.ts"
    video_file.write_bytes(b"x" * 1024)

    now = time.time()
    db.create_recording(
        {
            "id": "rec_cast",
            "title": "Cast Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 3000,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    fake_session = MagicMock()
    fake_session.session_id = "sess_dvr_cast"
    create_session_mock = AsyncMock(return_value=fake_session)
    monkeypatch.setattr(dvr_streaming.hls_streaming, "create_session", create_session_mock)

    response = client.post(
        "/api/dvr/recording-stream-hls",
        json={"url": str(video_file), "recording_id": "rec_cast", "for_cast": True},
    )

    assert response.status_code == 200
    body = response.json()
    cast_token = create_session_mock.await_args.kwargs["cast_token"]
    assert cast_token is not None
    assert body["playlist_url"] == f"/api/hls/sess_dvr_cast/{cast_token}/playlist.m3u8"


def test_recording_stream_hls_without_for_cast_omits_cast_token(client, tmp_db, tmp_path, monkeypatch):
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "finished.ts"
    video_file.write_bytes(b"x" * 1024)

    now = time.time()
    db.create_recording(
        {
            "id": "rec_no_cast",
            "title": "No Cast Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 3000,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    fake_session = MagicMock()
    fake_session.session_id = "sess_dvr_native"
    create_session_mock = AsyncMock(return_value=fake_session)
    monkeypatch.setattr(dvr_streaming.hls_streaming, "create_session", create_session_mock)

    response = client.post(
        "/api/dvr/recording-stream-hls",
        json={"url": str(video_file), "recording_id": "rec_no_cast"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["playlist_url"] == "/api/hls/sess_dvr_native/playlist.m3u8"
    assert create_session_mock.await_args.kwargs["cast_token"] is None


def test_estimate_byte_offset_aligns_to_ts_packet_boundary(tmp_path, monkeypatch):
    """`_estimate_byte_offset`'s raw seconds->bytes arithmetic almost never
    lands on a 188-byte MPEG-TS packet boundary; feeding pump_tail_follow an
    unaligned offset desyncs every subsequent packet it reads and corrupts
    the downstream ffmpeg's parse (regression guard for the 502-on-resume
    bug: 'Invalid frame dimensions 0x0' / 'PES packet size mismatch')."""
    video_file = tmp_path / "cap.ts"
    video_file.write_bytes(b"x" * 10_000)

    fixed_now = 1_700_000_000.0
    monkeypatch.setattr(dvr_api.time, "time", lambda: fixed_now)

    capture = MagicMock()
    capture.file_path = video_file
    capture.start_ts = fixed_now - 10  # elapsed=10s, file_size=10000 -> 1000 B/s

    # target_start_seconds=1.0 -> raw arithmetic offset is 1000, which is NOT
    # a multiple of 188 (1000 / 188 = 5.319...) - this is exactly the case
    # that previously corrupted playback.
    offset = dvr_streaming._estimate_byte_offset(capture, 1.0)
    assert offset == 940  # (1000 // 188) * 188
    assert offset % dvr_streaming._TS_PACKET_SIZE == 0
    assert offset <= 1000


def test_recording_stream_hls_aligns_resume_offset_to_ts_packet_boundary(client, tmp_db, tmp_path, monkeypatch):
    """Resuming/scrubbing into a still-recording capture must hand
    pump_tail_follow a 188-byte-aligned start_offset_bytes - an unaligned
    offset is what caused 'PES packet size mismatch' / 'Packet corrupt'
    ffmpeg errors and a 502 on recording resume (regression guard)."""
    from app.dvr.builtin.capture import ActiveCapture, capture_pipeline

    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local"})

    video_file = tmp_path / "live.ts"
    video_file.write_bytes(b"x" * (dvr_streaming._LIVE_CAPTURE_READY_MIN_BYTES + 1_000))

    now = time.time()
    active_capture = ActiveCapture(
        recording_id="rec_resume",
        scheduled_id=None,
        rule_id=None,
        channel_number="4.1",
        channel_name="WNBC",
        title="Live Show",
        episode_title=None,
        season_number=None,
        episode_number=None,
        start_ts=now - 10,
        end_ts=now + 600,
        file_path=video_file,
        image_url=None,
        process=None,
    )
    capture_pipeline._active_captures["rec_resume"] = active_capture

    captured_kwargs: dict = {}
    _spy_on_build_ffmpeg_args(monkeypatch, captured_kwargs)

    fake_session = MagicMock()
    fake_session.session_id = "sess_resume"

    async def _fake_create_session(*args, **kwargs):
        on_process_spawned = kwargs["on_process_spawned"]
        on_process_spawned(_fake_transcode_process())
        return fake_session

    monkeypatch.setattr(dvr_streaming.hls_streaming, "create_session", _fake_create_session)

    pump_kwargs: dict = {}

    async def _fake_pump_tail_follow(*args, **kwargs):
        pump_kwargs.update(kwargs)
        return None

    monkeypatch.setattr(dvr_streaming, "pump_tail_follow", _fake_pump_tail_follow)

    try:
        response = client.post(
            "/api/dvr/recording-stream-hls",
            json={"url": str(video_file), "recording_id": "rec_resume", "start": 1.0},
        )
        assert response.status_code == 200
        offset = pump_kwargs.get("start_offset_bytes")
        assert offset is not None
        assert offset % dvr_streaming._TS_PACKET_SIZE == 0
    finally:
        capture_pipeline._active_captures.pop("rec_resume", None)


def test_recording_stream_direct_mode_forces_transcode_when_audio_index_provided(client, tmp_db, tmp_path, monkeypatch):
    """When playback_mode is external/direct, requesting audio_index must route
    through ffmpeg transcoding so the stream mapping actually occurs."""
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local", "playback_mode": "external"}
    )
    video_file = tmp_path / "finished_direct.ts"
    video_file.write_bytes(b"MPEG-TS data" * 100)

    spawn_mock = AsyncMock(side_effect=lambda *a, **kw: _fake_transcode_process())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_mock)

    response = client.get(
        "/api/dvr/recording-stream",
        params={"url": str(video_file), "audio_index": 1},
    )
    assert response.status_code == 200
    assert spawn_mock.called
    args = list(spawn_mock.call_args[0])
    assert "-map" in args
    assert "0:v:0" in args
    assert "0:a:1" in args

