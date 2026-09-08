from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth import get_current_admin, hash_pin
from app.storage.db import (
    create_user,
    delete_sessions_for_user,
    delete_user,
    get_user,
    list_users,
    update_user,
)

router = APIRouter(prefix="/api/admin/users", tags=["admin"])

PIN_PATTERN = r"^\d{4,8}$"


class CreateHouseholdUserRequest(BaseModel):
    name: str
    avatar: str | None = None
    pin: str | None = Field(default=None, pattern=PIN_PATTERN)
    role: Literal["admin", "member"] = "member"


class UpdateHouseholdUserRequest(BaseModel):
    name: str | None = None
    avatar: str | None = None
    role: Literal["admin", "member"] | None = None
    pin: str | None = Field(default=None, pattern=r"^$|^\d{4,8}$")


class UpdateRoleRequest(BaseModel):
    role: Literal["admin", "member"]


def _admin_user_shape(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": user["id"],
        "name": user["name"],
        "avatar": user["avatar"],
        "has_pin": bool(user["pin_hash"]),
        "role": user["role"],
        "created_at": user["created_at"],
    }


@router.get("")
async def list_household_users(_: dict[str, Any] = Depends(get_current_admin)):
    users = await asyncio.to_thread(list_users)
    return [_admin_user_shape(u) for u in users]


@router.post("")
async def create_household_user(
    payload: CreateHouseholdUserRequest,
    _: dict[str, Any] = Depends(get_current_admin),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    pin_hash = pin_salt = pin_iterations = None
    if payload.pin:
        pin_hash, pin_salt, pin_iterations = hash_pin(payload.pin)

    user_id = uuid4().hex
    now = datetime.now(UTC).isoformat()
    avatar = payload.avatar.strip() if payload.avatar else None

    await asyncio.to_thread(
        create_user,
        user_id,
        name,
        avatar,
        pin_hash,
        pin_salt,
        pin_iterations,
        now,
        role=payload.role,
    )
    user = await asyncio.to_thread(get_user, user_id)
    return _admin_user_shape(user)


@router.patch("/{user_id}")
async def update_household_user(
    user_id: str,
    payload: UpdateHouseholdUserRequest,
    _: dict[str, Any] = Depends(get_current_admin),
):
    users = await asyncio.to_thread(list_users)
    target = next((u for u in users if u["id"] == user_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile '{user_id}'")

    fields: dict[str, Any] = {}
    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        fields["name"] = name

    if payload.avatar is not None:
        fields["avatar"] = payload.avatar.strip() if payload.avatar else None

    if payload.role is not None:
        if payload.role != "admin":
            admin_count = sum(1 for u in users if u["role"] == "admin")
            if target["role"] == "admin" and admin_count <= 1:
                raise HTTPException(status_code=400, detail="Can't remove the last remaining admin")
        fields["role"] = payload.role

    if "pin" in payload.model_fields_set:
        if payload.pin == "":
            fields.update(pin_hash=None, pin_salt=None, pin_iterations=None)
            await asyncio.to_thread(delete_sessions_for_user, user_id)
        elif payload.pin is not None:
            pin_hash, pin_salt, pin_iterations = hash_pin(payload.pin)
            fields.update(pin_hash=pin_hash, pin_salt=pin_salt, pin_iterations=pin_iterations)
            await asyncio.to_thread(delete_sessions_for_user, user_id)

    if fields:
        await asyncio.to_thread(update_user, user_id, **fields)

    updated = await asyncio.to_thread(get_user, user_id)
    return _admin_user_shape(updated)


@router.patch("/{user_id}/role")
async def update_role(user_id: str, payload: UpdateRoleRequest, admin: dict[str, Any] = Depends(get_current_admin)):
    users = await asyncio.to_thread(list_users)
    target = next((u for u in users if u["id"] == user_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile '{user_id}'")

    if payload.role != "admin":
        admin_count = sum(1 for u in users if u["role"] == "admin")
        if target["role"] == "admin" and admin_count <= 1:
            raise HTTPException(status_code=400, detail="Can't remove the last remaining admin")

    await asyncio.to_thread(update_user, user_id, role=payload.role)
    updated = {**target, "role": payload.role}
    return _admin_user_shape(updated)


@router.delete("/{user_id}")
async def remove_user(user_id: str, admin: dict[str, Any] = Depends(get_current_admin)):
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="Use DELETE /api/users/me to remove your own profile")

    users = await asyncio.to_thread(list_users)
    target = next((u for u in users if u["id"] == user_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Unknown profile '{user_id}'")

    if target["role"] == "admin":
        admin_count = sum(1 for u in users if u["role"] == "admin")
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Can't remove the last remaining admin")

    await asyncio.to_thread(delete_user, user_id)
    return {"status": "ok"}
