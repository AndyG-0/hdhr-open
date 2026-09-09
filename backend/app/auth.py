"""User identity: PIN hashing, session cookies, and the FastAPI
dependencies that resolve "who is asking" for each request.

Deliberately lightweight — this is a profile picker for a shared household
screen, not an internet-facing account system. See PIN handling below for
the threat model this is sized for.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, Request, Response

from app.config import settings
from app.storage.db import get_auth_token_by_hash, get_session, get_user, touch_auth_token

SESSION_COOKIE_NAME = "hdhropen_session"
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 90  # 90 days — long enough a kiosk screen doesn't re-prompt often

# PBKDF2-HMAC-SHA256 with 210k iterations (OWASP's current baseline for that
# combination) protects a short PIN behind a self-hosted, LAN-scoped app —
# no argon2/bcrypt dependency is justified for this threat model, and this
# stays stdlib-only like the rest of the backend.
_PBKDF2_ITERATIONS = 210_000


def hash_pin(pin: str) -> tuple[str, str, int]:
    """Returns (hash_hex, salt_hex, iterations) for storage."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return digest.hex(), salt.hex(), _PBKDF2_ITERATIONS


def verify_pin(pin: str, pin_hash: str, pin_salt: str, iterations: int) -> bool:
    digest = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), bytes.fromhex(pin_salt), iterations)
    return hmac.compare_digest(digest.hex(), pin_hash)


def hash_token(token: str) -> str:
    """A plain, unsalted SHA-256 digest for bearer-token storage.

    Unlike a PIN, a bearer token is `new_token()` output — 256 bits of
    CSPRNG entropy — so it isn't brute-forceable from its hash the way a
    short numeric PIN would be; PBKDF2's per-guess slowdown buys nothing
    here and would only slow down every authenticated request.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# In-memory sliding-window lockout for PIN login. A household kiosk doesn't
# need a durable/DB-backed counter (a backend restart clearing it is fine);
# it just needs to stop someone standing at the screen from brute-forcing a
# 4-digit PIN, which this fully covers since state doesn't need to survive
# restarts or be shared across processes.
_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_WINDOW_SECONDS = 60.0
_failed_attempts: dict[str, list[float]] = {}

# Same in-memory sliding-window shape, keyed by client IP instead of user_id,
# guarding get_current_user's bearer-token/session-cookie resolution against
# a scripted credential-stuffing loop. Much higher threshold and shared
# window since this guards a per-request path, not a manual PIN pad.
_IP_MAX_FAILED_ATTEMPTS = 200
_ip_failed_attempts: dict[str, list[float]] = {}

# _recent_failures only prunes the one key it's asked about, so a key that
# fails once and is never retried would otherwise sit in the dict forever.
# This bounds that growth (e.g. a scripted probe cycling through many
# distinct bogus user_ids or source IPs) by sweeping every key on a timer
# instead of only the one currently being read/written.
_SWEEP_INTERVAL_SECONDS = 300.0
_last_sweep_at = 0.0


def _recent_failures(store: dict[str, list[float]], key: str, window_seconds: float) -> list[float]:
    attempts = store.get(key)
    if not attempts:
        return []
    cutoff = time.monotonic() - window_seconds
    fresh = [t for t in attempts if t >= cutoff]
    if fresh:
        store[key] = fresh
    else:
        store.pop(key, None)
    return fresh


def _record_failure(store: dict[str, list[float]], key: str, window_seconds: float) -> None:
    _recent_failures(store, key, window_seconds)
    store.setdefault(key, []).append(time.monotonic())
    _sweep_stale_entries_if_due()


def _sweep_stale_entries_if_due() -> None:
    global _last_sweep_at
    now = time.monotonic()
    if now - _last_sweep_at < _SWEEP_INTERVAL_SECONDS:
        return
    _last_sweep_at = now
    stores = (_failed_attempts, _ip_failed_attempts)
    for store, window_seconds in ((s, _LOCKOUT_WINDOW_SECONDS) for s in stores):
        cutoff = now - window_seconds
        for key in [k for k, attempts in store.items() if not any(t >= cutoff for t in attempts)]:
            store.pop(key, None)


def is_locked_out(user_id: str) -> bool:
    return len(_recent_failures(_failed_attempts, user_id, _LOCKOUT_WINDOW_SECONDS)) >= _MAX_FAILED_ATTEMPTS


def record_failed_login(user_id: str) -> None:
    _record_failure(_failed_attempts, user_id, _LOCKOUT_WINDOW_SECONDS)


def record_successful_login(user_id: str) -> None:
    _failed_attempts.pop(user_id, None)


def _is_ip_locked_out(client_ip: str) -> bool:
    return len(_recent_failures(_ip_failed_attempts, client_ip, _LOCKOUT_WINDOW_SECONDS)) >= _IP_MAX_FAILED_ATTEMPTS


def _record_ip_failure(client_ip: str) -> None:
    _record_failure(_ip_failed_attempts, client_ip, _LOCKOUT_WINDOW_SECONDS)


def new_token() -> str:
    """A random, unguessable id used as both a row's primary key and its
    bearer credential (device ids and session ids double as cookie values).
    """
    return secrets.token_urlsafe(32)


def set_session_cookie(response: Response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        max_age=SESSION_COOKIE_MAX_AGE,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME)


async def get_current_session(request: Request) -> dict[str, Any]:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session = await asyncio.to_thread(get_session, session_id) if session_id else None
    if session is None or session["expires_at"] < datetime.now(UTC).isoformat():
        raise HTTPException(status_code=401, detail="Not logged in")
    return session


_BEARER_PREFIX = "bearer "


async def _resolve_bearer_token(request: Request) -> dict[str, Any] | None:
    """Resolves an `Authorization: Bearer ...` header to its auth_tokens row.

    Returns None (falls through to cookie auth) when the header is absent —
    a native client that authenticates this way never has to also carry the
    session/device cookies. An invalid or revoked token raises rather than
    falling through, so a stale token fails loudly instead of silently
    downgrading to an unrelated cookie session.
    """
    header = request.headers.get("Authorization", "")
    if not header.lower().startswith(_BEARER_PREFIX):
        return None
    token = header[len(_BEARER_PREFIX) :].strip()
    token_row = await asyncio.to_thread(get_auth_token_by_hash, hash_token(token)) if token else None
    if token_row is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked token")
    await asyncio.to_thread(touch_auth_token, token_row["id"], datetime.now(UTC).isoformat())
    return token_row


async def get_current_user(request: Request) -> dict[str, Any]:
    client_ip = request.client.host if request.client else "unknown"
    if _is_ip_locked_out(client_ip):
        raise HTTPException(status_code=429, detail="Too many failed auth attempts, try again shortly")
    try:
        token_row = await _resolve_bearer_token(request)
        if token_row is not None:
            user_id = token_row["user_id"]
        else:
            session = await get_current_session(request)
            user_id = session["user_id"]
        user = await asyncio.to_thread(get_user, user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="Not logged in")
    except HTTPException as exc:
        if exc.status_code != 429:
            _record_ip_failure(client_ip)
        raise
    return user


async def get_current_admin(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def require_write_access(plugin: Any, user: dict[str, Any]) -> None:
    # "network"-scope settings (NAS/router/media-server credentials, ...) are
    # shared by the whole household — only an admin may change them. Any
    # logged-in user may still read them (enforced by the login dependency on
    # the GET routes). "personal"-scope settings are each user's own, so no
    # extra check is needed beyond being logged in as that user. Takes
    # `plugin` as `Any` (not `Plugin`) to avoid a circular import between this
    # module and app.plugins.base — every call site passes a real Plugin
    # instance or class, both of which expose `settings_scope`.
    if plugin.settings_scope == "network" and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


def session_expiry() -> str:
    return (datetime.now(UTC) + timedelta(seconds=SESSION_COOKIE_MAX_AGE)).isoformat()
