from __future__ import annotations

from fastapi import APIRouter, Depends

from app.auth import get_current_user

router = APIRouter(prefix="/api/theme", tags=["theme"], dependencies=[Depends(get_current_user)])

_THEMES = [
    {"id": "light", "name": "Light"},
    {"id": "dark", "name": "Dark"},
    {"id": "sepia", "name": "Sepia"},
    {"id": "contrast", "name": "High Contrast"},
    {"id": "forest", "name": "Forest"},
    {"id": "ocean", "name": "Ocean"},
]


@router.get("")
async def get_theme():
    return {"themes": _THEMES, "default": "dark"}
