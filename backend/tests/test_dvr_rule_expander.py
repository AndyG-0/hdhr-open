from __future__ import annotations

import time
import uuid

from app.dvr.builtin.rule_expander import (
    _SINGLE_RULE_FALLBACK_GRACE_SECONDS,
    _index_scheduled,
    _is_already_recorded_or_scheduled,
    _keyword_matches,
    _match_airing,
    _title_matches,
    cleanup_expired_single_rules,
    expand_rules_sync,
    normalize_title,
)
from app.storage import db


def test_normalize_title():
    assert normalize_title("  The   Office   ") == "the office"
    assert normalize_title("Breaking Bad") == "breaking bad"


def test_dedup_catches_entries_straddling_a_bucket_boundary():
    # start_ts=299 and start_ts=549 land in different 300s-aligned buckets
    # (0 and 1) but are only 250s apart, well within the 300s tolerance.
    by_channel_bucket: dict = {}
    by_rule_bucket: dict = {}
    _index_scheduled(
        {"channel_id": "ch1", "rule_id": "rule1", "start_ts": 299.0},
        by_channel_bucket,
        by_rule_bucket,
    )

    assert _is_already_recorded_or_scheduled(
        "rule1", "ch1", 549.0, "Some Show", None, None, None, by_channel_bucket, by_rule_bucket, {}, {}
    )


def test_dedup_does_not_match_entries_exactly_300s_apart():
    by_channel_bucket: dict = {}
    by_rule_bucket: dict = {}
    _index_scheduled(
        {"channel_id": "ch1", "rule_id": "rule1", "start_ts": 0.0},
        by_channel_bucket,
        by_rule_bucket,
    )

    assert not _is_already_recorded_or_scheduled(
        "rule1", "ch1", 300.0, "Some Show", None, None, None, by_channel_bucket, by_rule_bucket, {}, {}
    )


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


def test_title_matches_exact_mode():
    assert _title_matches("College Football", "college   football", "exact")
    assert not _title_matches("College Football", "College Football: Ohio State", "exact")
    assert not _title_matches("", "College Football", "exact")
    assert not _title_matches("College Football", "", "exact")


def test_title_matches_contains_mode():
    assert _title_matches("College Football", "College Football: Ohio State at Michigan", "contains")
    assert not _title_matches("College Football", "NFL Football", "contains")


def test_keyword_matches_no_filter_matches_everything():
    assert _keyword_matches(None, {"synopsis": "anything"})
    assert _keyword_matches("", {"synopsis": "anything"})
    assert _keyword_matches("   ", {"synopsis": "anything"})


def test_keyword_matches_single_term_across_fields():
    assert _keyword_matches("Ohio State", {"synopsis": "Ohio State at Michigan", "title": "College Football"})
    assert _keyword_matches("Ohio State", {"episode_title": "Ohio State vs California"})
    assert _keyword_matches("Ohio State", {"category": "Ohio State Sports"})
    assert not _keyword_matches("Ohio State", {"synopsis": "Michigan at Penn State"})


def test_keyword_matches_is_case_and_whitespace_insensitive():
    assert _keyword_matches("ohio   state", {"synopsis": "Ohio State at Michigan"})


def test_keyword_matches_multi_term_is_or():
    query = "Ohio State, Michigan"
    assert _keyword_matches(query, {"synopsis": "Ohio State at Purdue"})
    assert _keyword_matches(query, {"synopsis": "Michigan at Purdue"})
    assert not _keyword_matches(query, {"synopsis": "Purdue at Indiana"})


def test_match_airing_legacy_rules_unaffected_by_new_fields():
    # A rule created before the migration has no title_match_mode/keyword_query
    # keys at all; a rule created after has them explicitly set to their
    # defaults ('exact', None). Both must behave identically to pre-existing
    # exact title matching.
    program = {"title": "Local News at 6", "external_program_id": None}
    legacy_rule = {"title": "Local News at 6", "series_match_key": "local news at 6"}
    modern_rule_with_defaults = {
        "title": "Local News at 6",
        "series_match_key": "local news at 6",
        "title_match_mode": "exact",
        "keyword_query": None,
    }
    assert _match_airing(legacy_rule, program)
    assert _match_airing(modern_rule_with_defaults, program)
    assert not _match_airing(legacy_rule, {"title": "Local News at 11", "external_program_id": None})


def test_match_airing_contains_mode_with_keyword_filter():
    rule = {
        "title": "College Football",
        "series_match_key": None,
        "title_match_mode": "contains",
        "keyword_query": "Ohio State",
    }
    matching = {"title": "College Football", "synopsis": "Ohio State at Michigan", "external_program_id": None}
    non_matching = {"title": "College Football", "synopsis": "Purdue at Indiana", "external_program_id": None}
    other_show = {"title": "NFL Football", "synopsis": "Ohio State at Michigan", "external_program_id": None}
    assert _match_airing(rule, matching)
    assert not _match_airing(rule, non_matching)
    assert not _match_airing(rule, other_show)


def test_expand_rules_keyword_rule_matches_only_synopsis_containing_keyword(tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "5.1", "KTLA", True)
    now = time.time()

    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "xmltv",
                "external_program_id": None,
                "title": "College Football",
                "episode_title": None,
                "season_number": None,
                "episode_number": None,
                "synopsis": "Ohio State at Michigan.",
                "start_ts": now + 1000,
                "end_ts": now + 5000,
                "original_air_date": None,
                "image_url": None,
                "is_new": 1,
                "category": "Sports",
            },
            {
                "channel_id": channel_id,
                "source_provider": "xmltv",
                "external_program_id": None,
                "title": "College Football",
                "episode_title": None,
                "season_number": None,
                "episode_number": None,
                "synopsis": "Purdue at Indiana.",
                "start_ts": now + 10000,
                "end_ts": now + 14000,
                "original_air_date": None,
                "image_url": None,
                "is_new": 1,
                "category": "Sports",
            },
        ]
    )

    rule_id = "rule_cfb_ohio_state"
    db.create_recording_rule(
        {
            "id": rule_id,
            "provider": "builtin",
            "type": "series",
            "title": "College Football",
            "series_match_key": "college football",
            "channel_id": "5.1",
            "new_only": False,
            "title_match_mode": "exact",
            "keyword_query": "Ohio State",
        }
    )

    scheduled = expand_rules_sync()
    assert len(scheduled) == 1
    assert scheduled[0]["synopsis"] == "Ohio State at Michigan."


def _make_single_rule(rule_id: str, target_ts: float, **overrides) -> dict:
    rule = {
        "id": rule_id,
        "provider": "builtin",
        "type": "single",
        "title": "Movie Night",
        "series_match_key": str(int(target_ts)),
        "channel_id": "7.1",
    }
    rule.update(overrides)
    db.create_recording_rule(rule)
    return rule


def test_cleanup_deletes_single_rule_once_its_recording_is_done(tmp_db):
    now = time.time()
    rule = _make_single_rule("rule_single_done", now - 7200)
    db.upsert_scheduled_recording(
        {
            "id": "sched_1",
            "rule_id": rule["id"],
            "channel_id": "ch1",
            "title": "Movie Night",
            "start_ts": now - 7200,
            "end_ts": now - 3600,
            "status": "completed",
        }
    )

    deleted = cleanup_expired_single_rules([rule], db.list_scheduled_recordings(), now)

    assert deleted == {rule["id"]}
    assert db.get_recording_rule(rule["id"]) is None


def test_cleanup_keeps_single_rule_with_pending_scheduled_recording(tmp_db):
    now = time.time()
    rule = _make_single_rule("rule_single_pending", now + 3600)
    db.upsert_scheduled_recording(
        {
            "id": "sched_2",
            "rule_id": rule["id"],
            "channel_id": "ch1",
            "title": "Movie Night",
            "start_ts": now + 3600,
            "end_ts": now + 7200,
            "status": "scheduled",
        }
    )

    deleted = cleanup_expired_single_rules([rule], db.list_scheduled_recordings(), now)

    assert deleted == set()
    assert db.get_recording_rule(rule["id"]) is not None


def test_cleanup_leaves_series_rules_alone(tmp_db):
    now = time.time()
    rule = {
        "id": "rule_series",
        "provider": "builtin",
        "type": "series",
        "title": "Nightly News",
        "series_match_key": "nightly news",
        "channel_id": "4.1",
    }
    db.create_recording_rule(rule)
    db.upsert_scheduled_recording(
        {
            "id": "sched_3",
            "rule_id": rule["id"],
            "channel_id": "ch1",
            "title": "Nightly News",
            "start_ts": now - 7200,
            "end_ts": now - 3600,
            "status": "completed",
        }
    )

    deleted = cleanup_expired_single_rules([rule], db.list_scheduled_recordings(), now)

    assert deleted == set()
    assert db.get_recording_rule(rule["id"]) is not None


def test_cleanup_deletes_single_rule_never_scheduled_after_grace_period(tmp_db):
    now = time.time()
    rule = _make_single_rule(
        "rule_single_never_scheduled", now - _SINGLE_RULE_FALLBACK_GRACE_SECONDS - 1
    )

    deleted = cleanup_expired_single_rules([rule], [], now)

    assert deleted == {rule["id"]}
    assert db.get_recording_rule(rule["id"]) is None


def test_cleanup_keeps_single_rule_never_scheduled_within_grace_period(tmp_db):
    now = time.time()
    rule = _make_single_rule("rule_single_recent", now - 60)

    deleted = cleanup_expired_single_rules([rule], [], now)

    assert deleted == set()
    assert db.get_recording_rule(rule["id"]) is not None


def test_expand_rules_sync_cleans_up_expired_single_rule(tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "4.1", "WNBC", True)
    now = time.time()

    rule = _make_single_rule("rule_single_stale", now - 7200)
    db.upsert_scheduled_recording(
        {
            "id": "sched_stale",
            "rule_id": rule["id"],
            "channel_id": channel_id,
            "title": "Movie Night",
            "start_ts": now - 7200,
            "end_ts": now - 3600,
            "status": "completed",
        }
    )

    expand_rules_sync()

    assert db.get_recording_rule(rule["id"]) is None
