"""Users, devices, sessions, auth tokens, and per-user preferences.

No FK constraints here (no table in `connection._SCHEMA` uses one, and
`_connect()` never sets `PRAGMA foreign_keys=ON`). Cascades on delete are
driven by the two registries below instead of a hand-written DELETE per
table.
"""

from __future__ import annotations

import json
from typing import Any

from app.storage.db.connection import _connect, _upsert, _validate_update_columns

# Allow-lists for the dynamic `UPDATE ... SET {columns}` helpers below
# (update_user/update_device), which build their SQL from **fields keys. No
# caller passes attacker-controlled key names today, but at least one
# (update_user, via app/api/users.py) already builds its kwargs from a
# Pydantic model's `model_dump()` rather than literal field names — this
# guards against a future caller doing that with an unvalidated dict. `id`
# (and `created_at`, where present) are deliberately excluded: no update_*
# function is ever called with those.
_USER_UPDATABLE_COLUMNS = frozenset({"name", "avatar", "pin_hash", "pin_salt", "pin_iterations", "role"})
_DEVICE_UPDATABLE_COLUMNS = frozenset({"name", "last_seen_at"})

_USER_SCOPED_TABLES: tuple[tuple[str, str], ...] = (
    ("sessions", "user_id"),
    ("auth_tokens", "user_id"),
    ("user_preferences", "user_id"),
)

_DEVICE_SCOPED_TABLES: tuple[tuple[str, str], ...] = (
    ("sessions", "device_id"),
    ("auth_tokens", "device_id"),
)


def create_user(
    id: str,
    name: str,
    avatar: str | None,
    pin_hash: str | None,
    pin_salt: str | None,
    pin_iterations: int | None,
    created_at: str,
    role: str = "member",
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users (id, name, avatar, pin_hash, pin_salt, pin_iterations, created_at, role) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (id, name, avatar, pin_hash, pin_salt, pin_iterations, created_at, role),
        )


def get_user(user_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return None if row is None else dict(row)


def list_users() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
    return [dict(row) for row in rows]


def update_user(user_id: str, **fields: Any) -> None:
    if not fields:
        return
    _validate_update_columns("users", _USER_UPDATABLE_COLUMNS, fields)
    columns = ", ".join(f"{key} = ?" for key in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE users SET {columns} WHERE id = ?", (*fields.values(), user_id))


def delete_user(user_id: str) -> None:
    with _connect() as conn:
        for table, column in _USER_SCOPED_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def create_device(id: str, name: str, created_at: str, last_seen_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO devices (id, name, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
            (id, name, created_at, last_seen_at),
        )


def get_device(device_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return None if row is None else dict(row)


def list_devices() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY created_at ASC").fetchall()
    return [dict(row) for row in rows]


def update_device(device_id: str, **fields: Any) -> None:
    if not fields:
        return
    _validate_update_columns("devices", _DEVICE_UPDATABLE_COLUMNS, fields)
    columns = ", ".join(f"{key} = ?" for key in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE devices SET {columns} WHERE id = ?", (*fields.values(), device_id))


def touch_device(device_id: str, last_seen_at: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE devices SET last_seen_at = ? WHERE id = ?", (last_seen_at, device_id))


def delete_device(device_id: str) -> None:
    with _connect() as conn:
        for table, column in _DEVICE_SCOPED_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (device_id,))
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))


def create_session(id: str, user_id: str, device_id: str, created_at: str, expires_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, user_id, device_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (id, user_id, device_id, created_at, expires_at),
        )


def get_session(session_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return None if row is None else dict(row)


def delete_session(session_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def delete_sessions_for_user(user_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def delete_sessions_for_device(device_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE device_id = ?", (device_id,))


def delete_expired_sessions(now: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))


# Bearer tokens for native clients — see the auth_tokens table comment in
# connection.py. The raw token is generated by the caller
# (app.auth.new_token()) and shown to the user exactly once, at issuance;
# only its hash is ever persisted.


def create_auth_token(id: str, user_id: str, device_id: str, token_hash: str, name: str, created_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO auth_tokens (id, user_id, device_id, token_hash, name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (id, user_id, device_id, token_hash, name, created_at),
        )


def get_auth_token_by_hash(token_hash: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM auth_tokens WHERE token_hash = ? AND revoked_at IS NULL", (token_hash,)
        ).fetchone()
    return None if row is None else dict(row)


def touch_auth_token(token_id: str, last_used_at: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE auth_tokens SET last_used_at = ? WHERE id = ?", (last_used_at, token_id))


def list_auth_tokens(user_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM auth_tokens WHERE user_id = ? AND revoked_at IS NULL ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def revoke_auth_token(token_id: str, revoked_at: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE auth_tokens SET revoked_at = ? WHERE id = ?", (revoked_at, token_id))


_DEFAULT_PREFERENCES: dict[str, Any] = {
    "theme": "dark",
    "locale": "en",
}


def get_user_preferences(user_id: str) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT preferences FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
    overrides = json.loads(row["preferences"]) if row else {}
    return {**_DEFAULT_PREFERENCES, **overrides}


def save_user_preferences(user_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge `overrides` onto the user's stored preferences and persist the result."""
    merged = {**get_user_preferences(user_id), **overrides}
    with _connect() as conn:
        _upsert(conn, "user_preferences", {"user_id": user_id, "preferences": json.dumps(merged)}, ("user_id",))
    return merged
