from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth import (
    SESSION_COOKIE_NAME,
    clear_session_cookie,
    get_current_user,
    hash_pin,
    hash_token,
    is_locked_out,
    new_token,
    record_failed_login,
    record_successful_login,
    session_expiry,
    set_session_cookie,
    verify_pin,
)
from app.storage.db import (
    create_auth_token,
    create_session,
    create_user,
    delete_expired_sessions,
    delete_session,
    delete_user,
    get_user,
    get_user_preferences,
    list_auth_tokens,
    list_users,
    revoke_auth_token,
    save_user_preferences,
    update_user,
)

router = APIRouter(prefix="/api/users", tags=["users"])

PIN_PATTERN = r"^\d{4,8}$"


class CreateUserRequest(BaseModel):
    name: str
    avatar: str | None = None
    pin: str | None = Field(default=None, pattern=PIN_PATTERN)


class LoginRequest(BaseModel):
    pin: str | None = None
    # Set by native clients (iOS/tvOS/Android/Android TV) that can't rely on
    # a cookie jar to additionally mint a bearer token for this login, valid
    # until revoked via DELETE /api/users/me/tokens/{id}. The value is a
    # human-readable label for that token ("Andy's iPhone"), shown back in
    # GET /api/users/me/tokens.
    token_name: str | None = None


class UpdateUserRequest(BaseModel):
    name: str | None = None
    avatar: str | None = None
    # "" clears an existing PIN (same convention as settings.py's secret
    # clearing); anything else must look like a PIN.
    pin: str | None = Field(default=None, pattern=r"^$|^\d{4,8}$")


class UpdatePreferencesRequest(BaseModel):
    theme: str | None = None
    locale: str | None = None


def _profile_shape(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "name": user["name"],
        "avatar": user["avatar"],
        "has_pin": bool(user["pin_hash"]),
    }


def user_shape(user: dict[str, Any]) -> dict[str, Any]:
    return {"id": user["id"], "name": user["name"], "avatar": user["avatar"], "role": user["role"]}


@router.get("")
async def list_profiles():
    users = await asyncio.to_thread(list_users)
    return [_profile_shape(u) for u in users]


@router.post("")
async def create_profile(payload: CreateUserRequest, response: Response):
    pin_hash = pin_salt = None
    pin_iterations = None
    if payload.pin:
        pin_hash, pin_salt, pin_iterations = hash_pin(payload.pin)

    user_id = uuid4().hex
    now = datetime.now(UTC).isoformat()
    await asyncio.to_thread(create_user, user_id, payload.name, payload.avatar, pin_hash, pin_salt, pin_iterations, now)

    session_id = new_token()
    await asyncio.to_thread(create_session, session_id, user_id, now, session_expiry())
    set_session_cookie(response, session_id)

    return user_shape({"id": user_id, "name": payload.name, "avatar": payload.avatar, "role": "member"})


@router.post("/{user_id}/login")
async def login(user_id: str, payload: LoginRequest, response: Response):
    user = await asyncio.to_thread(get_user, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile '{user_id}'")

    if user["pin_hash"]:
        if is_locked_out(user_id):
            raise HTTPException(status_code=429, detail="Too many incorrect attempts. Try again shortly.")
        if not payload.pin or not verify_pin(payload.pin, user["pin_hash"], user["pin_salt"], user["pin_iterations"]):
            record_failed_login(user_id)
            raise HTTPException(status_code=401, detail="Incorrect PIN")
        record_successful_login(user_id)

    session_id = new_token()
    now = datetime.now(UTC).isoformat()
    # Login (profile switch) is the natural, frequent moment to reap sessions
    # that expired since they were created — nothing else ever purges them.
    await asyncio.to_thread(delete_expired_sessions, now)
    await asyncio.to_thread(create_session, session_id, user["id"], now, session_expiry())
    set_session_cookie(response, session_id)

    result = user_shape(user)
    if payload.token_name:
        token = new_token()
        await asyncio.to_thread(create_auth_token, uuid4().hex, user["id"], hash_token(token), payload.token_name, now)
        # The raw token is returned exactly once, here — only its hash is
        # ever persisted, the same convention as a PIN.
        result["token"] = token
    return result


@router.post("/logout")
async def logout(request: Request, response: Response):
    # Reads the cookie directly (rather than depending on get_current_user)
    # so logging out an already-expired/invalid session still clears the
    # cookie instead of 401ing.
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        await asyncio.to_thread(delete_session, session_id)
    clear_session_cookie(response)
    return {"status": "ok"}


@router.get("/me")
async def current_profile(user: dict[str, Any] = Depends(get_current_user)):
    return user_shape(user)


@router.patch("/me")
async def update_profile(payload: UpdateUserRequest, user: dict[str, Any] = Depends(get_current_user)):
    fields = payload.model_dump(exclude_unset=True, exclude={"pin"})
    if "pin" in payload.model_fields_set:
        if payload.pin == "":
            fields.update(pin_hash=None, pin_salt=None, pin_iterations=None)
        elif payload.pin is not None:
            pin_hash, pin_salt, pin_iterations = hash_pin(payload.pin)
            fields.update(pin_hash=pin_hash, pin_salt=pin_salt, pin_iterations=pin_iterations)
    if fields:
        await asyncio.to_thread(update_user, user["id"], **fields)
    updated = await asyncio.to_thread(get_user, user["id"])
    return user_shape(updated)


@router.delete("/me")
async def delete_profile(user: dict[str, Any] = Depends(get_current_user)):
    all_users = await asyncio.to_thread(list_users)
    if len(all_users) <= 1:
        raise HTTPException(status_code=400, detail="Can't delete the only remaining profile")
    await asyncio.to_thread(delete_user, user["id"])
    return {"status": "ok"}


def _token_shape(token: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": token["id"],
        "name": token["name"],
        "created_at": token["created_at"],
        "last_used_at": token["last_used_at"],
    }


@router.get("/me/tokens")
async def list_my_tokens(user: dict[str, Any] = Depends(get_current_user)):
    tokens = await asyncio.to_thread(list_auth_tokens, user["id"])
    return [_token_shape(t) for t in tokens]


@router.delete("/me/tokens/{token_id}")
async def revoke_my_token(token_id: str, user: dict[str, Any] = Depends(get_current_user)):
    tokens = await asyncio.to_thread(list_auth_tokens, user["id"])
    if not any(t["id"] == token_id for t in tokens):
        raise HTTPException(status_code=404, detail=f"Unknown token '{token_id}'")
    await asyncio.to_thread(revoke_auth_token, token_id, datetime.now(UTC).isoformat())
    return {"status": "ok"}


@router.get("/me/preferences")
async def get_preferences(user: dict[str, Any] = Depends(get_current_user)):
    return await asyncio.to_thread(get_user_preferences, user["id"])


@router.patch("/me/preferences")
async def update_preferences(payload: UpdatePreferencesRequest, user: dict[str, Any] = Depends(get_current_user)):
    overrides = payload.model_dump(exclude_unset=True)
    return await asyncio.to_thread(save_user_preferences, user["id"], overrides)
