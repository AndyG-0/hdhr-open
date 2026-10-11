from __future__ import annotations

import time
import uuid

from app.dvr.builtin import discovery
from app.storage import db


def _make_channel(number: str, name: str) -> str:
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, number, name, True)
    return channel_id


def _upsert_program(channel_id: str, **overrides):
    program = {
        "channel_id": channel_id,
        "source_provider": "xmltv",
        "external_program_id": None,
        "title": "Some Show",
        "episode_title": None,
        "season_number": None,
        "episode_number": None,
        "synopsis": None,
        "start_ts": time.time() + 3600,
        "end_ts": time.time() + 5400,
        "original_air_date": None,
        "image_url": None,
        "is_new": 1,
        "category": "Comedy",
    }
    program.update(overrides)
    db.upsert_guide_programs([program])


def test_build_taste_profile_empty_with_no_recordings(tmp_db):
    profile = discovery.build_taste_profile()
    assert profile.has_data is False
    assert profile.category_weights == {}


def test_build_taste_profile_weights_categories_from_history(tmp_db):
    now = time.time()
    db.create_recording(
        {
            "id": "rec_1",
            "title": "Breaking Bad",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 1800,
            "file_path": "/tmp/rec_1.ts",
            "status": "completed",
            "category": "Drama, Crime",
        }
    )

    profile = discovery.build_taste_profile(now)
    assert profile.has_data is True
    assert profile.category_weights["drama"] > 0
    assert profile.category_weights["crime"] > 0
    assert "breaking bad" in profile.recorded_titles


def test_get_discovery_recommendations_cold_start_falls_back_to_new_and_notable(tmp_db):
    channel_id = _make_channel("7.1", "KCRA")
    _upsert_program(channel_id, title="Premiere Night", is_new=1, category="Drama")

    result = discovery.get_discovery_recommendations()
    assert result["has_profile"] is False
    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "Premiere Night"
    assert result["items"][0]["bucket"] == "shows"
    assert result["items"][0]["source"] == "new_and_notable"


def test_get_discovery_recommendations_cold_start_excludes_reruns(tmp_db):
    channel_id = _make_channel("7.1", "KCRA")
    _upsert_program(channel_id, title="Rerun Episode", is_new=0, category="Drama")

    result = discovery.get_discovery_recommendations()
    assert result["has_profile"] is False
    assert result["items"] == []


def _candidate(i: int, channel_id: str, start_ts: float) -> dict:
    return {
        "channel_id": channel_id,
        "_channel_number": channel_id,
        "external_program_id": None,
        "title": f"Drama Show {i}",
        "episode_title": None,
        "season_number": None,
        "episode_number": None,
        "synopsis": None,
        "start_ts": start_ts,
        "end_ts": start_ts + 1800,
        "original_air_date": None,
        "image_url": None,
        "is_new": 1,
        "category": "Drama",
        "audio": None,
    }


def test_take_new_and_notable_respects_limit():
    now = time.time()
    candidates = [_candidate(i, f"ch{i}", now + i * 60) for i in range(10)]

    chosen_keys: set = set()
    picks: list = []
    taken = discovery._take_new_and_notable(candidates, "shows", chosen_keys, picks, {}, limit=5)
    assert taken == 5
    assert len(picks) == 5


def test_take_new_and_notable_caps_results_per_channel():
    now = time.time()
    candidates = [_candidate(i, "ch0", now + i * 60) for i in range(10)]

    chosen_keys: set = set()
    picks: list = []
    taken = discovery._take_new_and_notable(candidates, "shows", chosen_keys, picks, {}, limit=30)
    assert taken == discovery._FALLBACK_MAX_PER_CHANNEL


def test_is_major_network_rejects_cable_lookalikes():
    assert discovery._is_major_network("NBC") is True
    assert discovery._is_major_network("FOX") is True
    assert discovery._is_major_network("FOXNEWS") is False
    assert discovery._is_major_network("FOXSPORTS1") is False
    assert discovery._is_major_network("NBCSN") is False
    assert discovery._is_major_network(None) is False
    assert discovery._is_major_network("TBS") is False


def test_get_discovery_recommendations_personalized_scores_matching_category(tmp_db):
    now = time.time()
    db.create_recording(
        {
            "id": "rec_1",
            "title": "Breaking Bad",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 1800,
            "file_path": "/tmp/rec_1.ts",
            "status": "completed",
            "category": "Drama, Crime",
        }
    )

    channel_id = _make_channel("7.1", "KCRA")
    _upsert_program(channel_id, title="Another Crime Drama", is_new=0, category="Drama, Crime")
    _upsert_program(channel_id, title="Unrelated Cooking Show", is_new=0, category="Cooking")

    result = discovery.get_discovery_recommendations()
    assert result["has_profile"] is True
    titles = [item["title"] for item in result["items"]]
    assert "Another Crime Drama" in titles
    assert "Unrelated Cooking Show" not in titles


def test_get_discovery_recommendations_excludes_already_recorded_title(tmp_db):
    now = time.time()
    db.create_recording(
        {
            "id": "rec_1",
            "title": "Breaking Bad",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 1800,
            "file_path": "/tmp/rec_1.ts",
            "status": "completed",
            "category": "Drama, Crime",
        }
    )

    channel_id = _make_channel("7.1", "KCRA")
    _upsert_program(channel_id, title="Breaking Bad", is_new=0, category="Drama, Crime")

    result = discovery.get_discovery_recommendations()
    assert result["items"] == []


def test_build_rule_intent_profile_from_scheduled_recordings(tmp_db):
    db.create_recording_rule(
        {
            "id": "rule_1",
            "provider": "builtin",
            "type": "series",
            "title": "Nightly Sports Roundup",
            "channel_id": None,
            "start_padding_seconds": 0,
            "end_padding_seconds": 0,
            "new_only": False,
            "priority": 0,
        }
    )
    db.upsert_scheduled_recording(
        {
            "id": "sched_1",
            "rule_id": "rule_1",
            "channel_id": "ch0",
            "guide_program_id": None,
            "title": "Nightly Sports Roundup",
            "episode_title": None,
            "season_number": None,
            "episode_number": None,
            "synopsis": None,
            "image_url": None,
            "original_air_date": None,
            "category": "Sports",
            "start_ts": time.time() + 3600,
            "end_ts": time.time() + 5400,
            "status": "scheduled",
            "recording_id": None,
        }
    )

    profile = discovery.build_rule_intent_profile()
    assert profile.has_data is True
    assert profile.category_weights["sports"] > 0
    assert profile.bucket_weights["sports"] > 0


def test_build_rule_intent_profile_from_rule_with_no_scheduled_instances(tmp_db):
    db.create_recording_rule(
        {
            "id": "rule_1",
            "provider": "builtin",
            "type": "series",
            "title": "NBA Finals",
            "channel_id": None,
            "start_padding_seconds": 0,
            "end_padding_seconds": 0,
            "new_only": False,
            "priority": 0,
        }
    )

    profile = discovery.build_rule_intent_profile()
    assert profile.has_data is True
    assert profile.category_weights == {}
    assert profile.bucket_weights["sports"] > 0


def test_get_discovery_recommendations_falls_through_to_active_rule_when_bucket_has_no_history(tmp_db):
    now = time.time()
    db.create_recording(
        {
            "id": "rec_1",
            "title": "Breaking Bad",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 1800,
            "file_path": "/tmp/rec_1.ts",
            "status": "completed",
            "category": "Drama, Crime",
        }
    )

    db.create_recording_rule(
        {
            "id": "rule_1",
            "provider": "builtin",
            "type": "single",
            "title": "Weekend Movie Block",
            "channel_id": None,
            "start_padding_seconds": 0,
            "end_padding_seconds": 0,
            "new_only": False,
            "priority": 0,
        }
    )
    db.upsert_scheduled_recording(
        {
            "id": "sched_1",
            "rule_id": "rule_1",
            "channel_id": "ch0",
            "guide_program_id": None,
            "title": "Weekend Movie Block",
            "episode_title": None,
            "season_number": None,
            "episode_number": None,
            "synopsis": None,
            "image_url": None,
            "original_air_date": None,
            "category": "Movie",
            "start_ts": now + 3600,
            "end_ts": now + 5400,
            "status": "scheduled",
            "recording_id": None,
        }
    )

    channel_id = _make_channel("7.1", "KCRA")
    _upsert_program(channel_id, title="Oscar Winning Movie Marathon", is_new=0, category="Movie")

    result = discovery.get_discovery_recommendations()
    items_by_bucket = {item["bucket"]: item for item in result["items"]}
    assert "movies" in items_by_bucket
    assert items_by_bucket["movies"]["title"] == "Oscar Winning Movie Marathon"
    assert items_by_bucket["movies"]["source"] == "active_rule"


def test_get_discovery_recommendations_favorite_team_tier(tmp_db):
    now = time.time()
    channel_id = _make_channel("7.1", "KCRA")
    _upsert_program(
        channel_id,
        title="Lakers at Celtics",
        is_new=0,
        category="Sports",
        start_ts=now + 3600,
        end_ts=now + 7200,
    )

    db.create_sports_favorite(
        {
            "id": "fav_1",
            "kind": "team",
            "league": "nba",
            "espn_team_id": "13",
            "team_display_name": "Los Angeles Lakers",
            "enabled": True,
        }
    )
    db.save_network_channel_map_entry("ESPN", channel_id)
    db.upsert_tracked_event(
        {
            "espn_event_id": "event_1",
            "favorite_id": "fav_1",
            "recording_rule_id": None,
            "league": "nba",
            "start_ts": now + 3660,
            "network_name": "ESPN",
            "title_resolved": False,
        }
    )

    result = discovery.get_discovery_recommendations()
    items_by_bucket = {item["bucket"]: item for item in result["items"]}
    assert "sports" in items_by_bucket
    assert items_by_bucket["sports"]["title"] == "Lakers at Celtics"
    assert items_by_bucket["sports"]["source"] == "favorite_team"


def test_get_discovery_recommendations_network_pick_tier(tmp_db):
    now = time.time()
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True, affiliate="NBC")
    _upsert_program(
        channel_id,
        title="New NBC Premiere",
        is_new=1,
        category="Drama",
        start_ts=now + 3600,
        end_ts=now + 5400,
    )

    result = discovery.get_discovery_recommendations()
    items_by_bucket = {item["bucket"]: item for item in result["items"]}
    assert "shows" in items_by_bucket
    assert items_by_bucket["shows"]["title"] == "New NBC Premiere"
    assert items_by_bucket["shows"]["source"] == "network_pick"


def test_get_discovery_recommendations_excludes_airings_with_active_rule(tmp_db):
    now = time.time()
    db.create_recording(
        {
            "id": "rec_1",
            "title": "Breaking Bad",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": now - 3600,
            "end_ts": now - 1800,
            "file_path": "/tmp/rec_1.ts",
            "status": "completed",
            "category": "Drama, Crime",
        }
    )

    channel_id = _make_channel("7.1", "KCRA")
    _upsert_program(channel_id, title="Better Call Saul", is_new=0, category="Drama, Crime")

    db.create_recording_rule(
        {
            "id": "rule_1",
            "provider": "builtin",
            "type": "series",
            "title": "Better Call Saul",
            "channel_id": None,
            "start_padding_seconds": 0,
            "end_padding_seconds": 0,
            "new_only": False,
            "priority": 0,
        }
    )

    result = discovery.get_discovery_recommendations()
    assert result["items"] == []
