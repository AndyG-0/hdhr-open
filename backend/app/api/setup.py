from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.users import PIN_PATTERN, user_shape
from app.auth import get_current_device, hash_pin, new_token, session_expiry, set_session_cookie
from app.storage.db import create_session, create_user, list_users

router = APIRouter(prefix="/api/setup", tags=["setup"])


class CreateAdminRequest(BaseModel):
    name: str
    avatar: str | None = None
    pin: str | None = Field(default=None, pattern=PIN_PATTERN)


@router.get("/status")
async def setup_status():
    users = await asyncio.to_thread(list_users)
    return {"needs_setup": len(users) == 0}


@router.post("/admin")
async def create_admin(
    payload: CreateAdminRequest, response: Response, device: dict[str, Any] = Depends(get_current_device)
):
    # The only thing standing between this and a standing "grant myself
    # admin" backdoor — once any profile exists, onboarding is over.
    if await asyncio.to_thread(list_users):
        raise HTTPException(status_code=409, detail="Setup has already been completed")

    pin_hash = pin_salt = None
    pin_iterations = None
    if payload.pin:
        pin_hash, pin_salt, pin_iterations = hash_pin(payload.pin)

    user_id = uuid4().hex
    now = datetime.now(UTC).isoformat()
    await asyncio.to_thread(
        create_user, user_id, payload.name, payload.avatar, pin_hash, pin_salt, pin_iterations, now, "admin"
    )

    session_id = new_token()
    await asyncio.to_thread(create_session, session_id, user_id, device["id"], now, session_expiry())
    set_session_cookie(response, session_id)

    return user_shape({"id": user_id, "name": payload.name, "avatar": payload.avatar, "role": "admin"})
