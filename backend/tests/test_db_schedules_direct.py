from __future__ import annotations

import time

from app.storage import db


def test_sd_station_map_crud(tmp_db):
    channel_id = "test-channel-1"
    station_id = "12345"
    lineup_id = "USA-OTA-90210"

    assert db.get_sd_station_map(channel_id) is None
    assert db.list_sd_station_map() == []

    db.upsert_sd_station_map(channel_id, station_id, lineup_id)

    mapped = db.get_sd_station_map(channel_id)
    assert mapped is not None
    assert mapped["channel_id"] == channel_id
    assert mapped["station_id"] == station_id
    assert mapped["lineup_id"] == lineup_id

    assert len(db.list_sd_station_map()) == 1

    # Update
    db.upsert_sd_station_map(channel_id, "67890", lineup_id)
    mapped2 = db.get_sd_station_map(channel_id)
    assert mapped2["station_id"] == "67890"

    # Delete
    db.delete_sd_station_map(channel_id)
    assert db.get_sd_station_map(channel_id) is None
    assert db.list_sd_station_map() == []


def test_sd_program_cache(tmp_db):
    programs = [
        {
            "program_id": "EP001",
            "metadata": {"title": "Show 1", "description": "Episode 1"},
            "fetched_at": "2026-08-01T00:00:00Z",
        },
        {
            "program_id": "EP002",
            "metadata": {"title": "Show 2", "description": "Episode 2"},
            "fetched_at": "2026-08-15T00:00:00Z",
        },
    ]

    db.upsert_sd_program_cache(programs)

    cached = db.get_cached_sd_programs(["EP001", "EP002", "EP003"])
    assert "EP001" in cached
    assert cached["EP001"]["metadata"]["title"] == "Show 1"
    assert "EP002" in cached
    assert cached["EP002"]["metadata"]["title"] == "Show 2"
    assert "EP003" not in cached

    # Delete expired
    db.delete_expired_sd_program_cache("2026-08-10T00:00:00Z")
    after_expired = db.get_cached_sd_programs(["EP001", "EP002"])
    assert "EP001" not in after_expired
    assert "EP002" in after_expired


def test_resolve_guide_programs_with_schedules_direct(tmp_db):
    now = time.time()
    ch1 = {"id": "c1", "channel_number": "2.1", "name": "CBS", "guide_provider": None}
    ch2 = {"id": "c2", "channel_number": "4.1", "name": "NBC", "guide_provider": "schedules_direct"}

    rows = [
        # Channel 1: only has schedules_direct
        {
            "channel_id": "c1",
            "source_provider": "schedules_direct",
            "external_program_id": "EP100",
            "title": "SD Morning News",
            "episode_title": None,
            "season_number": None,
            "episode_number": None,
            "synopsis": "News",
            "start_ts": now,
            "end_ts": now + 3600,
            "original_air_date": None,
            "image_url": None,
            "is_new": 0,
            "category": "News",
        },
        # Channel 2: has hdhomerun_cloud AND schedules_direct, but pinned to schedules_direct
        {
            "channel_id": "c2",
            "source_provider": "hdhomerun_cloud",
            "external_program_id": "HD100",
            "title": "HD Today",
            "episode_title": None,
            "season_number": None,
            "episode_number": None,
            "synopsis": "Morning show",
            "start_ts": now,
            "end_ts": now + 3600,
            "original_air_date": None,
            "image_url": None,
            "is_new": 0,
            "category": "Talk",
        },
        {
            "channel_id": "c2",
            "source_provider": "schedules_direct",
            "external_program_id": "EP200",
            "title": "SD Pinned Today",
            "episode_title": None,
            "season_number": None,
            "episode_number": None,
            "synopsis": "Morning show from SD",
            "start_ts": now,
            "end_ts": now + 3600,
            "original_air_date": None,
            "image_url": None,
            "is_new": 0,
            "category": "Talk",
        },
    ]

    resolved = db.resolve_guide_programs([ch1, ch2], rows)
    assert len(resolved["c1"]) == 1
    assert resolved["c1"][0]["title"] == "SD Morning News"

    assert len(resolved["c2"]) == 1
    assert resolved["c2"][0]["title"] == "SD Pinned Today"
