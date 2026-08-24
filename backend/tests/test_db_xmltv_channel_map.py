from __future__ import annotations

from app.storage import db


def test_upsert_xmltv_channel_map_creates_row(tmp_db):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    db.upsert_xmltv_channel_map("ch1", "wnbc.us", "NBC New York")

    row = db.get_xmltv_channel_map("ch1")

    assert row["xmltv_channel_id"] == "wnbc.us"
    assert row["display_name"] == "NBC New York"


def test_upsert_xmltv_channel_map_updates_on_conflict(tmp_db):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    db.upsert_xmltv_channel_map("ch1", "wnbc.us", "NBC New York")

    db.upsert_xmltv_channel_map("ch1", "wnbc2.us", "NBC")

    row = db.get_xmltv_channel_map("ch1")
    assert row["xmltv_channel_id"] == "wnbc2.us"
    assert row["display_name"] == "NBC"


def test_get_xmltv_channel_map_returns_none_when_missing(tmp_db):
    assert db.get_xmltv_channel_map("missing") is None


def test_list_xmltv_channel_map_returns_all_rows(tmp_db):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    db.upsert_channel("ch2", "5.1", "WABC", True)
    db.upsert_xmltv_channel_map("ch1", "wnbc.us", None)
    db.upsert_xmltv_channel_map("ch2", "wabc.us", None)

    rows = db.list_xmltv_channel_map()

    assert {row["channel_id"] for row in rows} == {"ch1", "ch2"}


def test_delete_xmltv_channel_map_removes_row(tmp_db):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    db.upsert_xmltv_channel_map("ch1", "wnbc.us", None)

    db.delete_xmltv_channel_map("ch1")

    assert db.get_xmltv_channel_map("ch1") is None
