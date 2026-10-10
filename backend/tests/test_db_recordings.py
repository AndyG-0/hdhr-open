from __future__ import annotations

from app.storage import db
from app.storage.cache import cache


def _make_recording(rec_id: str, title: str, start_ts: float, status: str = "completed") -> dict:
    return {
        "id": rec_id,
        "title": title,
        "channel_id": "4.1",
        "channel_name_snapshot": "WNBC",
        "start_ts": start_ts,
        "end_ts": start_ts + 1800,
        "file_path": f"/tmp/{rec_id}.ts",
        "status": status,
    }


def test_list_completed_recordings_filters_status_and_orders_ascending(tmp_db):
    db.create_recording(_make_recording("r1", "Show A", 3000.0))
    db.create_recording(_make_recording("r2", "Show B", 1000.0))
    db.create_recording(_make_recording("r3", "Show C", 2000.0, status="recording"))

    result = db.list_completed_recordings()

    assert [r["id"] for r in result] == ["r2", "r1"]


def test_list_completed_recordings_by_title_matches_case_and_whitespace_insensitively(tmp_db):
    db.create_recording(_make_recording("r1", "  Daily News  ", 2000.0))
    db.create_recording(_make_recording("r2", "DAILY NEWS", 1000.0))
    db.create_recording(_make_recording("r3", "Other Show", 1500.0))
    db.create_recording(_make_recording("r4", "Daily News", 500.0, status="recording"))

    result = db.list_completed_recordings_by_title("daily news")

    assert [r["id"] for r in result] == ["r2", "r1"]


def test_search_recordings_matches_title_case_insensitively(tmp_db):
    db.create_recording(_make_recording("r1", "The Daily Show", 2000.0))
    db.create_recording(_make_recording("r2", "Other Program", 1000.0))

    result = db.search_recordings(search="daily")

    assert [r["id"] for r in result] == ["r1"]


def test_search_recordings_matches_synopsis_category_and_channel(tmp_db):
    rec = _make_recording("r1", "Show A", 2000.0)
    rec["synopsis"] = "A story about a lighthouse keeper"
    db.create_recording(rec)
    db.create_recording(_make_recording("r2", "Show B", 1000.0))

    assert [r["id"] for r in db.search_recordings(search="lighthouse")] == ["r1"]
    assert [r["id"] for r in db.search_recordings(search="wnbc")] == ["r1", "r2"]


def test_search_recordings_escapes_like_wildcards(tmp_db):
    db.create_recording(_make_recording("r1", "100% Wolf", 2000.0))
    db.create_recording(_make_recording("r2", "Anything Goes", 1000.0))

    result = db.search_recordings(search="100%")

    assert [r["id"] for r in result] == ["r1"]


def test_search_recordings_no_term_returns_everything_ordered(tmp_db):
    db.create_recording(_make_recording("r1", "Show A", 1000.0))
    db.create_recording(_make_recording("r2", "Show B", 2000.0))

    result = db.search_recordings()

    assert [r["id"] for r in result] == ["r2", "r1"]


def test_search_recordings_paginates_with_limit_and_offset(tmp_db):
    for i, ts in enumerate([1000.0, 2000.0, 3000.0]):
        db.create_recording(_make_recording(f"r{i}", f"Show {i}", ts))

    page = db.search_recordings(limit=2, offset=1)

    assert [r["id"] for r in page] == ["r1", "r0"]


def test_create_update_delete_recording_invalidate_cache(tmp_db):
    cache.set("dvr_recordings:::None:0", ["stale"], ttl_seconds=60)
    db.create_recording(_make_recording("r1", "Show A", 1000.0))
    assert cache.get("dvr_recordings:::None:0") is None

    cache.set("dvr_recordings:::None:0", ["stale"], ttl_seconds=60)
    db.update_recording("r1", title="Show A Renamed")
    assert cache.get("dvr_recordings:::None:0") is None

    cache.set("dvr_recordings:::None:0", ["stale"], ttl_seconds=60)
    db.delete_recording("r1")
    assert cache.get("dvr_recordings:::None:0") is None


def test_update_recording_heartbeat_only_does_not_invalidate_cache(tmp_db):
    db.create_recording(_make_recording("r1", "Show A", 1000.0, status="recording"))
    cache.set("dvr_recordings:::None:0", ["cached"], ttl_seconds=60)

    db.update_recording("r1", last_heartbeat_at=1234.0)

    assert cache.get("dvr_recordings:::None:0") == ["cached"]
