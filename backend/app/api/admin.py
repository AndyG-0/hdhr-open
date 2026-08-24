from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_admin
from app.storage.db import delete_user, list_users, update_user

router = APIRouter(prefix="/api/admin/users", tags=["admin"])


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
