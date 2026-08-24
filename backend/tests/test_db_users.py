from __future__ import annotations

from app.storage import db


def _create(user_id="alice", name="Alice", avatar=None, pin_hash=None, pin_salt=None, pin_iterations=None):
    db.create_user(user_id, name, avatar, pin_hash, pin_salt, pin_iterations, "2026-01-01T00:00:00Z")


def test_get_user_returns_none_when_unset(tmp_db):
    assert db.get_user("nope") is None


def test_create_then_get_user_round_trips(tmp_db):
    _create(avatar="cat.png", pin_hash="h", pin_salt="s", pin_iterations=210_000)

    user = db.get_user("alice")

    assert user["id"] == "alice"
    assert user["name"] == "Alice"
    assert user["avatar"] == "cat.png"
    assert user["pin_hash"] == "h"
    assert user["pin_salt"] == "s"
    assert user["pin_iterations"] == 210_000


def test_list_users_is_empty_on_a_fresh_install(tmp_db):
    assert db.list_users() == []


def test_list_users_returns_created_users(tmp_db):
    _create("alice", "Alice")

    ids = {u["id"] for u in db.list_users()}

    assert ids == {"alice"}


def test_update_user_changes_only_given_fields(tmp_db):
    _create()

    db.update_user("alice", name="Alicia")

    user = db.get_user("alice")
    assert user["name"] == "Alicia"
    assert user["avatar"] is None


def test_update_user_with_no_fields_is_a_noop(tmp_db):
    _create()

    db.update_user("alice")

    assert db.get_user("alice")["name"] == "Alice"


def test_delete_user_removes_the_user(tmp_db):
    _create()

    db.delete_user("alice")

    assert db.get_user("alice") is None


def test_delete_user_cascades_sessions_and_preferences(tmp_db):
    _create()
    db.create_device("dev1", "Kitchen", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z")
    db.create_session("sess1", "alice", "dev1", "2026-01-01T00:00:00Z", "2099-01-01T00:00:00Z")
    db.save_user_preferences("alice", {"theme": "light"})

    db.delete_user("alice")

    assert db.get_session("sess1") is None
    assert db.get_user_preferences("alice") == db._DEFAULT_PREFERENCES
