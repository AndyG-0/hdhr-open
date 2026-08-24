from __future__ import annotations

from app.storage import db


def _seed_user_and_device(user_id="alice", device_id="dev1"):
    db.create_user(user_id, "Alice", None, None, None, None, "2026-01-01T00:00:00Z")
    db.create_device(device_id, "Kitchen Tablet", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")


def test_get_session_returns_none_when_unset(tmp_db):
    assert db.get_session("nope") is None


def test_create_then_get_session_round_trips(tmp_db):
    _seed_user_and_device()

    db.create_session("sess1", "alice", "dev1", "2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")

    session = db.get_session("sess1")
    assert session["id"] == "sess1"
    assert session["user_id"] == "alice"
    assert session["device_id"] == "dev1"
    assert session["expires_at"] == "2026-04-01T00:00:00Z"


def test_delete_session_removes_it(tmp_db):
    _seed_user_and_device()
    db.create_session("sess1", "alice", "dev1", "2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")

    db.delete_session("sess1")

    assert db.get_session("sess1") is None


def test_delete_sessions_for_user_only_removes_that_users_sessions(tmp_db):
    _seed_user_and_device("alice", "dev1")
    _seed_user_and_device("bob", "dev2")
    db.create_session("sess-alice", "alice", "dev1", "2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")
    db.create_session("sess-bob", "bob", "dev2", "2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")

    db.delete_sessions_for_user("alice")

    assert db.get_session("sess-alice") is None
    assert db.get_session("sess-bob") is not None


def test_delete_sessions_for_device_only_removes_that_devices_sessions(tmp_db):
    _seed_user_and_device("alice", "dev1")
    db.create_device("dev2", "Living Room TV", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    db.create_session("sess-dev1", "alice", "dev1", "2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")
    db.create_session("sess-dev2", "alice", "dev2", "2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")

    db.delete_sessions_for_device("dev1")

    assert db.get_session("sess-dev1") is None
    assert db.get_session("sess-dev2") is not None
