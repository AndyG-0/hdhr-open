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


def test_get_discovery_recommendations_cold_start_excludes_reruns(tmp_db):
    channel_id = _make_channel("7.1", "KCRA")
    _upsert_program(channel_id, title="Rerun Episode", is_new=0, category="Drama")

    result = discovery.get_discovery_recommendations()
    assert result["has_profile"] is False
    assert result["items"] == []


def test_fallback_caps_results_per_bucket():
    now = time.time()
    candidates = [
        {
            "channel_id": f"ch{i}",
            "_channel_number": str(i),
            "external_program_id": None,
            "title": f"Drama Show {i}",
            "episode_title": None,
            "season_number": None,
            "episode_number": None,
            "synopsis": None,
            "start_ts": now + i * 60,
            "end_ts": now + i * 60 + 1800,
            "original_air_date": None,
            "image_url": None,
            "is_new": 1,
            "category": "Drama",
            "audio": None,
        }
        for i in range(10)
    ]

    items = discovery._fallback_new_and_notable(candidates, limit=30)
    assert len(items) == discovery._FALLBACK_MAX_PER_BUCKET


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
