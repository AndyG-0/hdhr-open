from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.auth import get_current_admin
from app.config import APP_SETTINGS_KEYS, SECRET_APP_SETTINGS_KEYS, effective_settings
from app.storage.db import save_app_settings

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(get_current_admin)])


class UpdateSettingsRequest(BaseModel):
    # `extra="forbid"` doubles as the allow-list: a key outside APP_SETTINGS_KEYS
    # is rejected with a 422 instead of being silently persisted.
    model_config = ConfigDict(extra="forbid")

    timezone: str | None = None
    guide_provider_priority: str | None = None
    dvr_server_priority: str | None = None
    sports_extension_enabled: str | None = None
    sports_extension_max_minutes: str | None = None


assert set(UpdateSettingsRequest.model_fields) == set(APP_SETTINGS_KEYS), (
    "UpdateSettingsRequest fields must mirror APP_SETTINGS_KEYS exactly"
)


def _public_shape(current: dict[str, Any]) -> dict[str, Any]:
    # Secrets are write-only: callers get a boolean "is it set", never the
    # raw value, so the key can't leak back out over the API.
    return {
        "timezone": current["timezone"],
        "guide_provider_priority": current.get("guide_provider_priority", "xmltv,schedules_direct,hdhomerun_cloud"),
        "dvr_server_priority": current.get("dvr_server_priority", "builtin,hdhomerun"),
        "sports_extension_enabled": current.get("sports_extension_enabled", "false"),
        "sports_extension_max_minutes": current.get("sports_extension_max_minutes", "240"),
        **{f"has_{key}": bool(current.get(key)) for key in SECRET_APP_SETTINGS_KEYS},
    }


@router.get("")
async def get_settings():
    return _public_shape(effective_settings())


@router.patch("")
async def update_settings(payload: UpdateSettingsRequest):
    # An empty string means "clear this key"; `save_app_settings` deletes
    # the override for any key mapped to None, falling back to the .env
    # default (or unset) on the next read. `exclude_unset` keeps this a
    # partial update — a key the client never sent stays untouched.
    overrides = {key: (value if value != "" else None) for key, value in payload.model_dump(exclude_unset=True).items()}
    await asyncio.to_thread(save_app_settings, overrides)
    return _public_shape(effective_settings())
