"""At-rest encryption for secret values in the `app_settings` table (API
keys, OAuth client secrets, CalDAV/iCloud passwords — see
`app.config.SECRET_APP_SETTINGS_KEYS`).

The key is a locally-generated Fernet key persisted at `SECRET_KEY_PATH`
(created on first use, 0600 permissions), not derived from anything else —
this only protects against someone reading the SQLite file directly (a
backup, a misconfigured volume mount, ...), not against someone who also has
the key file, so key and database should still be handled as equally
sensitive.
"""

from __future__ import annotations

import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from app.config import SECRET_KEY_PATH

logger = logging.getLogger(__name__)

# Marks a value as ciphertext so `decrypt` can tell it apart from a plaintext
# value written before this module existed (or restored from an old backup)
# and pass those through unchanged instead of raising.
_ENCRYPTED_PREFIX = "enc:v1:"

_key_cache: bytes | None = None


def _load_key() -> bytes:
    global _key_cache
    if _key_cache is not None:
        return _key_cache

    if SECRET_KEY_PATH.exists():
        _key_cache = SECRET_KEY_PATH.read_bytes()
        return _key_cache

    SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    SECRET_KEY_PATH.write_bytes(key)
    os.chmod(SECRET_KEY_PATH, 0o600)
    _key_cache = key
    return key


def reset_key_cache() -> None:
    """Drops the cached key so the next encrypt/decrypt re-reads SECRET_KEY_PATH.

    Only needed by tests that monkeypatch SECRET_KEY_PATH between cases —
    production code never changes the key path at runtime.
    """
    global _key_cache
    _key_cache = None


def encrypt(value: str) -> str:
    token = Fernet(_load_key()).encrypt(value.encode("utf-8")).decode("ascii")
    return _ENCRYPTED_PREFIX + token


def decrypt(value: str) -> str:
    """Reverses `encrypt`. A value without the marker prefix is returned
    as-is (see module docstring) rather than raising."""
    if not value.startswith(_ENCRYPTED_PREFIX):
        return value

    token = value[len(_ENCRYPTED_PREFIX) :].encode("ascii")
    try:
        return Fernet(_load_key()).decrypt(token).decode("utf-8")
    except InvalidToken:
        # The key file changed (or is missing/regenerated) since this value
        # was written — treat it as unreadable rather than crashing whatever
        # feature is trying to use it. Logged rather than silently swallowed:
        # this is exactly what a misconfigured deployment (SECRET_KEY_PATH
        # not pointed at persistent storage) looks like from the inside, and
        # without a trace it just presents as "my password disappeared".
        logger.warning(
            "Could not decrypt a stored secret — SECRET_KEY_PATH (%s) doesn't match the key it was "
            "encrypted with. If this follows a container/deployment recreation, SECRET_KEY_PATH is "
            "probably not pointed at persistent storage.",
            SECRET_KEY_PATH,
        )
        return ""
