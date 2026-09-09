"""App settings and network integration persistence."""

from __future__ import annotations

import json
from typing import Any

from app import crypto
from app.crypto import decrypt, encrypt
from app.storage.db.connection import _connect, _upsert


def get_app_settings() -> dict[str, str]:
    """Runtime overrides for global app config (timezone, ...), layered on
    top of the `.env`-backed `Settings` defaults — see `app.config.effective_settings`.

    A key whose stored value can't be decrypted (see `crypto.DecryptionError`)
    is omitted from the result rather than raising — callers already treat a
    missing key the same as "unconfigured" (e.g. `.get(key, default)`), so
    this degrades the same way a stale/rotated encryption key always has,
    just without silently returning a garbage empty string as if it were a
    real value.
    """
    from app.storage import db as _db

    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    result: dict[str, str] = {}
    for row in rows:
        if row["key"] not in _db.SECRET_APP_SETTINGS_KEYS:
            result[row["key"]] = row["value"]
            continue
        try:
            result[row["key"]] = decrypt(row["value"])
        except crypto.DecryptionError:
            continue
    return result


def save_app_settings(overrides: dict[str, str | None]) -> None:
    """Upsert app setting overrides; a `None` value clears that key."""
    from app.storage import db as _db

    with _connect() as conn:
        for key, value in overrides.items():
            if value is None:
                conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
            else:
                stored = encrypt(value) if key in _db.SECRET_APP_SETTINGS_KEYS else value
                _upsert(conn, "app_settings", {"key": key, "value": stored}, ("key",))


NETWORK_INTEGRATION_SECRET_KEYS = ("password", "api_key", "dvr_ssh_password", "dvr_ssh_key")


def _encrypt_network_integration_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {k: (encrypt(v) if k in NETWORK_INTEGRATION_SECRET_KEYS and v else v) for k, v in settings.items()}


def _decrypt_network_integration_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Mirrors `get_app_settings`'s handling of an undecryptable value: the
    key is omitted from the result rather than substituted with a sentinel,
    so a caller's `.get(key)` sees "not set" instead of a garbage `""`."""
    result: dict[str, Any] = {}
    for k, v in settings.items():
        if k not in NETWORK_INTEGRATION_SECRET_KEYS or not v:
            result[k] = v
            continue
        try:
            result[k] = decrypt(v)
        except crypto.DecryptionError:
            continue
    return result


def save_network_integration(id: str, type_: str, name: str, settings: dict[str, Any]) -> None:
    """Create or overwrite a network integration row (its full settings, not a partial merge — callers merge first)."""
    stored = _encrypt_network_integration_settings(settings)
    with _connect() as conn:
        _upsert(
            conn,
            "network_integrations",
            {"id": id, "type": type_, "name": name, "settings": json.dumps(stored)},
            ("id",),
        )


def get_network_integration(id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT id, type, name, settings FROM network_integrations WHERE id = ?", (id,)).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "type": row["type"],
        "name": row["name"],
        "settings": _decrypt_network_integration_settings(json.loads(row["settings"])),
    }


def list_network_integrations(type_: str | None = None) -> list[dict[str, Any]]:
    with _connect() as conn:
        if type_ is None:
            rows = conn.execute("SELECT id, type, name, settings FROM network_integrations").fetchall()
        else:
            rows = conn.execute(
                "SELECT id, type, name, settings FROM network_integrations WHERE type = ?", (type_,)
            ).fetchall()
    return [
        {
            "id": row["id"],
            "type": row["type"],
            "name": row["name"],
            "settings": _decrypt_network_integration_settings(json.loads(row["settings"])),
        }
        for row in rows
    ]


def delete_network_integration(id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM network_integrations WHERE id = ?", (id,))
