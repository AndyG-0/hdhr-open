from __future__ import annotations

from app.dvr.duplicates import duplicate_key, find_duplicate_groups

NOW = 10_000.0


def _rec(rec_id: str, **overrides):
    rec = {
        "recording_id": rec_id,
        "title": "Jeopardy!",
        "episode_title": "Game 1",
        "season_number": 40,
        "episode_number": "40.1",
        "original_air_date": "2026-08-18",
        "category_type": "shows",
        "start": 1000.0,
        "record_end": 2000.0,
        "status": "completed",
        "file_size_bytes": 100,
    }
    rec.update(overrides)
    return rec


def test_groups_matching_recordings():
    groups = find_duplicate_groups([_rec("a"), _rec("b"), _rec("c", episode_title="Game 2")], NOW)
    assert len(groups) == 1
    assert {r["recording_id"] for r in groups[0]["recordings"]} == {"a", "b"}


def test_normalizes_case_and_whitespace():
    groups = find_duplicate_groups([_rec("a"), _rec("b", title="  JEOPARDY! ", episode_title="game   1")], NOW)
    assert len(groups) == 1


def test_matches_builtin_and_official_episode_formats():
    official = _rec("b", season_number=None, episode_number="S40E01", provider="hdhomerun")
    assert len(find_duplicate_groups([_rec("a"), official], NOW)) == 1


def test_show_without_details_is_not_grouped():
    bare = {"episode_title": None, "season_number": None, "episode_number": None, "original_air_date": None}
    assert find_duplicate_groups([_rec("a", **bare), _rec("b", **bare)], NOW) == []


def test_movie_title_only_is_grouped():
    movie = {
        "title": "Casablanca",
        "category_type": "movies",
        "episode_title": None,
        "season_number": None,
        "episode_number": None,
        "original_air_date": None,
    }
    assert len(find_duplicate_groups([_rec("a", **movie), _rec("b", **movie)], NOW)) == 1


def test_different_air_dates_are_not_grouped():
    assert find_duplicate_groups([_rec("a"), _rec("b", original_air_date="2026-08-19")], NOW) == []


def test_excludes_in_progress_and_missing_ids():
    assert duplicate_key(_rec("a", record_end=None), NOW) is None
    assert duplicate_key(_rec("a", record_end=NOW + 60), NOW) is None
    assert duplicate_key(_rec("a", status="recording"), NOW) is None
    assert duplicate_key(_rec(""), NOW) is None
    assert find_duplicate_groups([_rec("a"), _rec("a", status="recording")], NOW) == []


def test_same_id_listed_twice_is_not_a_duplicate():
    assert find_duplicate_groups([_rec("a"), _rec("a")], NOW) == []


def test_suggested_keeper_tie_breaks():
    group = find_duplicate_groups([_rec("small", file_size_bytes=10), _rec("big", file_size_bytes=500)], NOW)[0]
    assert group["suggested_keep_id"] == "big"

    group = find_duplicate_groups(
        [_rec("short", duration_seconds=100), _rec("long", duration_seconds=200)],
        NOW,
    )[0]
    assert group["suggested_keep_id"] == "long"

    group = find_duplicate_groups([_rec("sd", video_height=480), _rec("hd", video_height=1080)], NOW)[0]
    assert group["suggested_keep_id"] == "hd"

    group = find_duplicate_groups([_rec("old", start=1000.0), _rec("new", start=1500.0)], NOW)[0]
    assert group["suggested_keep_id"] == "new"
    assert [r["recording_id"] for r in group["recordings"]] == ["new", "old"]
