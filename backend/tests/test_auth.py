from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app import auth
from app.storage import db


def test_hash_pin_then_verify_pin_round_trips():
    pin_hash, pin_salt, iterations = auth.hash_pin("1234")

    assert auth.verify_pin("1234", pin_hash, pin_salt, iterations) is True


def test_verify_pin_rejects_wrong_pin():
    pin_hash, pin_salt, iterations = auth.hash_pin("1234")

    assert auth.verify_pin("9999", pin_hash, pin_salt, iterations) is False


def test_hash_pin_uses_a_fresh_salt_each_call():
    hash_a, salt_a, _ = auth.hash_pin("1234")
    hash_b, salt_b, _ = auth.hash_pin("1234")

    assert salt_a != salt_b
    assert hash_a != hash_b


def test_new_token_returns_distinct_unguessable_values():
    assert auth.new_token() != auth.new_token()


class _FakeRequest:
    def __init__(self, cookies: dict[str, str], headers: dict[str, str] | None = None):
        self.cookies = cookies
        self.headers = headers or {}


async def test_get_current_session_raises_401_without_a_cookie(tmp_db):
    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_session(_FakeRequest({}))
    assert exc_info.value.status_code == 401


async def test_get_current_session_raises_401_for_an_expired_session(tmp_db):
    db.create_user("alice", "Alice", None, None, None, None, "2020-01-01T00:00:00Z")
    expired = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    db.create_session("sess1", "alice", "2020-01-01T00:00:00Z", expired)

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_session(_FakeRequest({auth.SESSION_COOKIE_NAME: "sess1"}))
    assert exc_info.value.status_code == 401


async def test_get_current_session_returns_the_session_when_valid(tmp_db):
    db.create_user("alice", "Alice", None, None, None, None, "2020-01-01T00:00:00Z")
    db.create_session("sess1", "alice", "2020-01-01T00:00:00Z", auth.session_expiry())

    session = await auth.get_current_session(_FakeRequest({auth.SESSION_COOKIE_NAME: "sess1"}))

    assert session["id"] == "sess1"
    assert session["user_id"] == "alice"


async def test_get_current_user_resolves_from_a_valid_session(tmp_db):
    db.create_user("alice", "Alice", None, None, None, None, "2020-01-01T00:00:00Z")
    db.create_session("sess1", "alice", "2020-01-01T00:00:00Z", auth.session_expiry())

    user = await auth.get_current_user(_FakeRequest({auth.SESSION_COOKIE_NAME: "sess1"}))

    assert user["id"] == "alice"


async def test_get_current_user_raises_401_when_the_user_row_is_gone(tmp_db):
    db.create_user("alice", "Alice", None, None, None, None, "2020-01-01T00:00:00Z")
    db.create_session("sess1", "alice", "2020-01-01T00:00:00Z", auth.session_expiry())
    db.delete_user("alice")

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_FakeRequest({auth.SESSION_COOKIE_NAME: "sess1"}))
    assert exc_info.value.status_code == 401


async def test_get_current_user_resolves_from_a_valid_bearer_token(tmp_db):
    db.create_user("alice", "Alice", None, None, None, None, "2020-01-01T00:00:00Z")
    db.create_auth_token("tok1", "alice", auth.hash_token("secret-token"), "Alice's iPhone", "2020-01-01T00:00:00Z")

    user = await auth.get_current_user(_FakeRequest({}, headers={"Authorization": "Bearer secret-token"}))

    assert user["id"] == "alice"


async def test_get_current_user_raises_401_for_an_unknown_bearer_token(tmp_db):
    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_FakeRequest({}, headers={"Authorization": "Bearer nope"}))
    assert exc_info.value.status_code == 401


async def test_get_current_user_raises_401_for_a_revoked_bearer_token(tmp_db):
    db.create_user("alice", "Alice", None, None, None, None, "2020-01-01T00:00:00Z")
    db.create_auth_token("tok1", "alice", auth.hash_token("secret-token"), "Alice's iPhone", "2020-01-01T00:00:00Z")
    db.revoke_auth_token("tok1", "2020-01-02T00:00:00Z")

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_user(_FakeRequest({}, headers={"Authorization": "Bearer secret-token"}))
    assert exc_info.value.status_code == 401


async def test_get_current_admin_returns_the_user_when_role_is_admin(tmp_db):
    db.create_user("alice", "Alice", None, None, None, None, "2020-01-01T00:00:00Z", role="admin")
    user = db.get_user("alice")

    admin = await auth.get_current_admin(user)

    assert admin["id"] == "alice"


async def test_get_current_admin_raises_403_for_a_member(tmp_db):
    db.create_user("bob", "Bob", None, None, None, None, "2020-01-01T00:00:00Z", role="member")
    user = db.get_user("bob")

    with pytest.raises(HTTPException) as exc_info:
        await auth.get_current_admin(user)
    assert exc_info.value.status_code == 403


def test_is_locked_out_is_false_with_no_recorded_failures():
    assert auth.is_locked_out("alice") is False


def test_is_locked_out_becomes_true_after_max_failed_attempts():
    for _ in range(auth._MAX_FAILED_ATTEMPTS):
        auth.record_failed_login("alice")

    assert auth.is_locked_out("alice") is True


def test_is_locked_out_stays_false_below_the_threshold():
    for _ in range(auth._MAX_FAILED_ATTEMPTS - 1):
        auth.record_failed_login("alice")

    assert auth.is_locked_out("alice") is False


def test_record_successful_login_clears_failed_attempts():
    for _ in range(auth._MAX_FAILED_ATTEMPTS):
        auth.record_failed_login("alice")

    auth.record_successful_login("alice")

    assert auth.is_locked_out("alice") is False


def test_lockout_expires_after_the_window_passes(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])

    for _ in range(auth._MAX_FAILED_ATTEMPTS):
        auth.record_failed_login("alice")
    assert auth.is_locked_out("alice") is True

    clock[0] += auth._LOCKOUT_WINDOW_SECONDS + 1

    assert auth.is_locked_out("alice") is False


def test_lockout_is_scoped_per_user_id():
    for _ in range(auth._MAX_FAILED_ATTEMPTS):
        auth.record_failed_login("alice")

    assert auth.is_locked_out("bob") is False


def test_periodic_sweep_prunes_a_stale_user_id_never_queried_again(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])

    # "alice" fails once and is never retried, so nothing ever calls
    # _recent_failures("alice") again to prune her entry directly.
    auth.record_failed_login("alice")
    assert "alice" in auth._failed_attempts

    clock[0] += auth._LOCKOUT_WINDOW_SECONDS + auth._SWEEP_INTERVAL_SECONDS + 1

    # Any other user's failed login is enough to trigger the periodic sweep.
    auth.record_failed_login("bob")

    assert "alice" not in auth._failed_attempts
