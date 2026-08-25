from __future__ import annotations

from app.storage import db


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
