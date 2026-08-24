from __future__ import annotations

from app.storage import db


def _create(device_id="dev1", name="Kitchen Tablet"):
    db.create_device(device_id, name, "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")


def test_get_device_returns_none_when_unset(tmp_db):
    assert db.get_device("nope") is None


def test_create_then_get_device_round_trips(tmp_db):
    _create()

    device = db.get_device("dev1")

    assert device["id"] == "dev1"
    assert device["name"] == "Kitchen Tablet"
    assert device["created_at"] == "2026-01-01T00:00:00Z"
    assert device["last_seen_at"] == "2026-01-01T00:00:00Z"


def test_list_devices_is_empty_on_a_fresh_install(tmp_db):
    assert db.list_devices() == []


def test_list_devices_returns_created_devices(tmp_db):
    _create("dev1", "Kitchen Tablet")

    ids = {d["id"] for d in db.list_devices()}

    assert ids == {"dev1"}


def test_update_device_changes_only_given_fields(tmp_db):
    _create()

    db.update_device("dev1", name="Renamed")

    assert db.get_device("dev1")["name"] == "Renamed"


def test_touch_device_bumps_last_seen_at(tmp_db):
    _create()

    db.touch_device("dev1", "2026-06-01T00:00:00Z")

    assert db.get_device("dev1")["last_seen_at"] == "2026-06-01T00:00:00Z"


def test_delete_device_removes_the_device(tmp_db):
    _create()

    db.delete_device("dev1")

    assert db.get_device("dev1") is None


def test_delete_device_cascades_sessions(tmp_db):
    _create()
    db.create_user("alice", "Alice", None, None, None, None, "2026-01-01T00:00:00Z")
    db.create_session("sess1", "alice", "dev1", "2026-01-01T00:00:00Z", "2099-01-01T00:00:00Z")

    db.delete_device("dev1")

    assert db.get_session("sess1") is None
