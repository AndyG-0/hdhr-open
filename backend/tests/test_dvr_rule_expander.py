from __future__ import annotations

import time
import uuid

import pytest

from app.dvr.builtin.rule_expander import expand_rules_sync, normalize_title
from app.storage import db


def test_normalize_title():
    assert normalize_title("  The   Office   ") == "the office"
    assert normalize_title("Breaking Bad") == "breaking bad"


def test_expand_rules_hdhomerun_series_rule(tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()

    # Seed guide programs with SiliconDust SeriesID
    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "hdhomerun_cloud",
                "external_program_id": "EP01234567",
                "title": "Jeopardy!",
                "episode_title": "Tournament of Champions",
                "season_number": 40,
                "episode_number": 150,
                "synopsis": "Trivia game.",
                "start_ts": now + 1000,
                "end_ts": now + 2800,
                "original_air_date": "2026-08-18",
                "image_url": "http://example.com/j.jpg",
                "is_new": 1,
                "category": "Game Show",
            }
        ]
    )

    # Create HDHomeRun-style rule matching on SeriesID
    rule_id = "rule_hdhr_1"
    db.create_recording_rule(
        {
            "id": rule_id,
            "provider": "builtin",
            "type": "series",
            "title": "Jeopardy!",
            "series_match_key": "EP01234567",
            "channel_id": "4.1",
            "start_padding_seconds": 60,
            "end_padding_seconds": 120,
            "new_only": True,
            "priority": 0,
        }
    )

    scheduled = expand_rules_sync()
    assert len(scheduled) == 1
    s = scheduled[0]
    assert s["rule_id"] == rule_id
    assert s["title"] == "Jeopardy!"
    assert s["episode_title"] == "Tournament of Champions"
    assert s["synopsis"] == "Trivia game."
    assert s["image_url"] == "http://example.com/j.jpg"
    assert s["season_number"] == 40
    assert s["episode_number"] == 150
    assert s["original_air_date"] == "2026-08-18"
    assert s["category"] == "Game Show"
    # Padded start (1000 - 60) and end (2800 + 120)
    assert s["start_ts"] == now + 1000 - 60
    assert s["end_ts"] == now + 2800 + 120

    # Running expand_rules again should not create duplicate
    scheduled_second_pass = expand_rules_sync()
    assert len(scheduled_second_pass) == 0


def test_expand_rules_xmltv_epg_title_rule(tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "9.1", "KCAL", True)
    now = time.time()

    # Seed guide programs from XMLTV (no vendor external_program_id)
    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "xmltv",
                "external_program_id": None,
                "title": "Local News at 6",
                "episode_title": "Evening Edition",
                "season_number": None,
                "episode_number": None,
                "synopsis": "Daily local news.",
                "start_ts": now + 3600,
                "end_ts": now + 5400,
                "original_air_date": "2026-08-18",
                "image_url": None,
                "is_new": 1,
                "category": "News",
            }
        ]
    )

    # Create EPG rule matching on normalized title
    rule_id = "rule_epg_news"
    db.create_recording_rule(
        {
            "id": rule_id,
            "provider": "builtin",
            "type": "series",
            "title": "local news at 6",
            "series_match_key": "local news at 6",
            "channel_id": "9.1",
            "start_padding_seconds": 0,
            "end_padding_seconds": 60,
            "new_only": False,
        }
    )

    scheduled = expand_rules_sync()
    assert len(scheduled) == 1
    assert scheduled[0]["title"] == "Local News at 6"
    assert scheduled[0]["channel_id"] == channel_id


def test_expand_rules_single_airing_rule(tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "7.1", "KABC", True)
    now = time.time()
    airing_start = now + 7200

    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "xmltv",
                "external_program_id": None,
                "title": "Movie Night: Inception",
                "episode_title": None,
                "season_number": None,
                "episode_number": None,
                "synopsis": "A thief steals secrets through dreams.",
                "start_ts": airing_start,
                "end_ts": airing_start + 9000,
                "original_air_date": "2010-07-16",
                "image_url": None,
                "is_new": 0,
                "category": "Movie",
            }
        ]
    )

    # Create single airing rule with DateTimeOnly
    rule_id = "rule_movie_single"
    db.create_recording_rule(
        {
            "id": rule_id,
            "provider": "builtin",
            "type": "single",
            "title": "Movie Night: Inception",
            "series_match_key": str(int(airing_start)),
            "channel_id": "7.1",
            "start_padding_seconds": 30,
            "end_padding_seconds": 300,
        }
    )

    scheduled = expand_rules_sync()
    assert len(scheduled) == 1
    assert scheduled[0]["title"] == "Movie Night: Inception"
    assert scheduled[0]["start_ts"] == airing_start - 30
    assert scheduled[0]["end_ts"] == airing_start + 9000 + 300


def test_expand_rules_skips_already_recorded_episodes(tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()

    # Pre-record S01E01
    db.create_recording(
        {
            "id": "rec_done_1",
            "title": "Sitcom Show",
            "episode_title": "Pilot",
            "season_number": 1,
            "episode_number": 1,
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 86400,
            "end_ts": now - 84600,
            "file_path": "/tmp/test.ts",
            "status": "completed",
        }
    )

    # Guide has S01E01 rerun (is_new=0) and S01E02 (is_new=1)
    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "hdhomerun_cloud",
                "external_program_id": "EP_SITCOM",
                "title": "Sitcom Show",
                "episode_title": "Pilot",
                "season_number": 1,
                "episode_number": 1,
                "synopsis": "Rerun.",
                "start_ts": now + 1000,
                "end_ts": now + 2800,
                "original_air_date": "2020-01-01",
                "image_url": None,
                "is_new": 0,
                "category": "Comedy",
            },
            {
                "channel_id": channel_id,
                "source_provider": "hdhomerun_cloud",
                "external_program_id": "EP_SITCOM",
                "title": "Sitcom Show",
                "episode_title": "Episode Two",
                "season_number": 1,
                "episode_number": 2,
                "synopsis": "New episode.",
                "start_ts": now + 3000,
                "end_ts": now + 4800,
                "original_air_date": "2026-08-18",
                "image_url": None,
                "is_new": 1,
                "category": "Comedy",
            },
        ]
    )

    db.create_recording_rule(
        {
            "id": "rule_sitcom",
            "provider": "builtin",
            "type": "series",
            "title": "Sitcom Show",
            "series_match_key": "EP_SITCOM",
            "channel_id": "4.1",
            "new_only": True,
        }
    )

    scheduled = expand_rules_sync()
    # S01E01 is skipped because it's not new and already completed; S01E02 is scheduled
    assert len(scheduled) == 1
    assert scheduled[0]["episode_title"] == "Episode Two"
