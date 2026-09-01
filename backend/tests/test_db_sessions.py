from __future__ import annotations

from app.storage import db


def _seed_user(user_id="alice"):
    db.create_user(user_id, "Alice", None, None, None, None, "2026-01-01T00:00:00Z")


def test_get_session_returns_none_when_unset(tmp_db):
    assert db.get_session("nope") is None


def test_create_then_get_session_round_trips(tmp_db):
    _seed_user()
    db.create_session("sess1", "alice", "2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")
    session = db.get_session("sess1")
    assert session["id"] == "sess1"
    assert session["user_id"] == "alice"
    assert session["expires_at"] == "2026-04-01T00:00:00Z"


def test_delete_session_removes_it(tmp_db):
    _seed_user()
    db.create_session("sess1", "alice", "2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")
    db.delete_session("sess1")
    assert db.get_session("sess1") is None


def test_delete_sessions_for_user_only_removes_that_users_sessions(tmp_db):
    _seed_user("alice")
    _seed_user("bob")
    db.create_session("sess-alice", "alice", "2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")
    db.create_session("sess-bob", "bob", "2026-01-01T00:00:00Z", "2026-04-01T00:00:00Z")
    db.delete_sessions_for_user("alice")
    assert db.get_session("sess-alice") is None
    assert db.get_session("sess-bob") is not None
