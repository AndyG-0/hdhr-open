"""Application settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent
# Overridable via env so a Docker deployment can point it at a volume-mounted
# directory (mounting a named volume directly onto a single file isn't
# possible) — see docker-compose.yml.
DB_PATH = Path(os.environ.get("DB_PATH", str(BACKEND_ROOT / "storage.db")))
# Symmetric key used to encrypt secret app_settings/network_integrations
# values at rest (see app.crypto). Overridable via env for the same reason
# as DB_PATH — must live in the same persistent volume as the database, or a
# redeploy that loses this file would strand every encrypted secret it holds.
SECRET_KEY_PATH = Path(os.environ.get("SECRET_KEY_PATH", str(BACKEND_ROOT / "secret.key")))
# Generated closed-caption WebVTT and scrub-bar thumbnail sprites for
# completed recordings, keyed by recording id (see app/dvr/media/).
# Overridable via env for the same reason as DB_PATH — must live in the same
# persistent volume, or every redeploy pays the ffmpeg/ffprobe cost again.
HDHOMERUN_MEDIA_CACHE_DIR = Path(
    os.environ.get("HDHOMERUN_MEDIA_CACHE_DIR", str(BACKEND_ROOT / "hdhomerun_media_cache"))
)
# Where the builtin DVR engine writes recorded MPEG-TS files. Deliberately
# separate from DB_PATH's small storage volume — ATSC OTA stream-copy runs
# roughly 2-4 GB/hour, so this typically points at a NAS mount or a big USB
# disk, not a Pi's boot media.
RECORDINGS_DIR = Path(os.environ.get("RECORDINGS_DIR", str(BACKEND_ROOT / "recordings")))
# Per-session temp directories for HLS packaging (app/hls_streaming.py) - each
# native-client playback session gets a subdirectory here holding its rolling
# window of ffmpeg-written segments + playlist. Ephemeral by design (sessions
# never need to survive a restart), but still overridable via env so a
# container without a writable BACKEND_ROOT can point it at a tmpfs/volume.
HLS_SESSION_DIR = Path(os.environ.get("HLS_SESSION_DIR", str(BACKEND_ROOT / "hls_sessions")))
HLS_SESSION_DIR.mkdir(parents=True, exist_ok=True)
# Rotating log files (see app/logging_config.py). Overridable via env for the
# same reason as DB_PATH - a redeploy that loses this directory loses the
# history of what the retention/disk-space safeguard did, which is exactly
# what you need after the fact to tell "it pruned recordings for space" from
# "something else deleted them".
LOG_DIR = Path(os.environ.get("LOG_DIR", str(BACKEND_ROOT / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # IANA timezone (e.g. "America/Chicago"), used anywhere the guide/DVR
    # needs to reason about "today" (rule expansion, the guide grid's date
    # headers).
    timezone: str = "UTC"

    # Comma-separated list of allowed browser origins for the frontend, e.g.
    # "http://localhost:5173,http://192.168.1.50:3000" — lets a kiosk and a
    # phone/desktop browser reach the same backend from different origins at
    # once, and lets frontend/backend run on different hosts without the
    # backend rejecting the frontend's actual origin. Native clients bypass
    # CORS entirely (it's a browser-only mechanism).
    cors_origin: str = "http://localhost:5173"

    # Flags for the device/session cookies (app/auth.py). Default to a
    # same-host, HTTP-friendly LAN deployment (frontend/backend split only by
    # port — cookie "site" ignores port, so SameSite=Lax still crosses that
    # split). If frontend and backend are deployed on genuinely different
    # hosts, cross-site cookies require SameSite=None + Secure, which in turn
    # requires real TLS — override both once a reverse proxy terminates it.
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    # Root logger level (standard `logging` names: "DEBUG", "INFO", "WARNING",
    # "ERROR"). See app/logging_config.py.
    log_level: str = "INFO"

    # Global default resolution order for guide data across providers
    # (comma-separated list of: "xmltv", "schedules_direct", "hdhomerun_cloud").
    guide_provider_priority: str = "xmltv,schedules_direct,hdhomerun_cloud"

    # Global default resolution order for recording servers
    # (comma-separated list of: "builtin", "hdhomerun").
    dvr_server_priority: str = "builtin,hdhomerun"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origin.split(",") if origin.strip()]


settings = Settings()

# Global settings a user can edit at runtime from the UI, keyed the same as
# the `Settings` fields above.
APP_SETTINGS_KEYS = ("timezone", "guide_provider_priority", "dvr_server_priority")

# The subset of APP_SETTINGS_KEYS that hold credentials/tokens rather than
# plain preferences — encrypted at rest by app.storage.db (see app.crypto)
# and never echoed back verbatim by the settings API. Empty for now: the
# secrets this app actually holds (Schedules Direct password, HDHomeRun DVR
# key) live in `network_integrations` instead — see app.api.network_settings.
SECRET_APP_SETTINGS_KEYS: tuple[str, ...] = ()


def effective_settings() -> dict[str, Any]:
    """`.env`-backed defaults with runtime (DB-persisted) overrides layered on top."""
    from app.storage.db import get_app_settings

    base = {key: getattr(settings, key) for key in APP_SETTINGS_KEYS}
    return {**base, **get_app_settings()}


def resolve_timezone(timezone_name: str) -> ZoneInfo:
    """A `ZoneInfo` for `timezone_name`, falling back to UTC if unrecognized."""
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def resolve_guide_provider_priority(raw_priority: str | None = None) -> tuple[str, ...]:
    """Parse comma-separated guide provider priority into a validated tuple of provider names."""
    valid_providers = ("xmltv", "schedules_direct", "hdhomerun_cloud")
    if raw_priority is None:
        raw_priority = effective_settings().get("guide_provider_priority", "xmltv,schedules_direct,hdhomerun_cloud")
    items = [p.strip() for p in raw_priority.split(",") if p.strip() in valid_providers]
    for p in valid_providers:
        if p not in items:
            items.append(p)
    return tuple(items)


def resolve_dvr_server_priority(raw_priority: str | None = None) -> tuple[str, ...]:
    """Parse comma-separated DVR server priority into a validated tuple of server names."""
    valid_servers = ("builtin", "hdhomerun")
    if raw_priority is None:
        raw_priority = effective_settings().get("dvr_server_priority", "builtin,hdhomerun")
    items = [p.strip() for p in raw_priority.split(",") if p.strip() in valid_servers]
    for p in valid_servers:
        if p not in items:
            items.append(p)
    return tuple(items)
