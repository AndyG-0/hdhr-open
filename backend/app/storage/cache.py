"""Simple in-memory TTL cache for widget summary/detail data."""

from __future__ import annotations

import time
from typing import Any


class TTLCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = (time.monotonic() + ttl_seconds, value)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def delete_prefix(self, prefix: str) -> None:
        """Drop every key starting with `prefix` — for invalidating cache
        entries fanned out across a dimension not known at delete time (e.g.
        one cached entry per device for a device-overridable setting)."""
        for key in [k for k in self._store if k.startswith(prefix)]:
            del self._store[key]


cache = TTLCache()
