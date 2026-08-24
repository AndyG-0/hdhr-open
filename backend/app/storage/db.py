"""SQLite persistence.

A plain, unpooled sqlite3 connection is enough here: this is a
single-backend, single-writer app (one household's HDHomeRun tuner), not a
multi-tenant service.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app.config import DB_PATH, SECRET_APP_SETTINGS_KEYS
from app.crypto import decrypt, encrypt

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    avatar TEXT,
    pin_hash TEXT,
    pin_salt TEXT,
    pin_iterations INTEGER,
    created_at TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member'
);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_device_id ON sessions (device_id);

-- Bearer tokens for native clients (iOS/tvOS/Android/Android TV/Fire TV),
-- issued alongside a session cookie at login. A system media pipeline
-- (AVPlayer/ExoPlayer) handed a raw stream URL doesn't reliably thread an
-- app's cookie jar the way a browser fetch does, and per-device revocation
-- ("remove this Apple TV") is a single row delete instead of hunting down a
-- shared cookie. Only `token_hash` is stored — the raw token is shown once,
-- at issuance, the same way a PIN's hash/salt work in `users` above.
CREATE TABLE IF NOT EXISTS auth_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    token_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_id ON auth_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_token_hash ON auth_tokens (token_hash);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    preferences TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- One shared, admin-edited connection config per external service: the
-- HDHomeRun tuner (+ its optional companion DVR engine), Schedules Direct,
-- or an XMLTV feed URL — one row per type, `id = type`. `settings` is a JSON
-- blob with `password`/`api_key` values Fernet-encrypted per-key (same
-- mechanism as app_settings, see app.crypto), not the whole column. See
-- app.api.network_settings.
CREATE TABLE IF NOT EXISTS network_integrations (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    name TEXT NOT NULL,
    settings TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_network_integrations_type ON network_integrations (type);

-- A tuner-numbered channel. Single-tuner v1: one lineup, refreshed from
-- `/lineup.json`. `guide_provider` pins this channel to one of
-- "hdhomerun_cloud" | "xmltv" | "schedules_direct", or NULL to use the
-- household's default provider priority — see app.guide.service.
CREATE TABLE IF NOT EXISTS channels (
    id TEXT PRIMARY KEY,
    channel_number TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_hd INTEGER NOT NULL DEFAULT 0,
    is_favorite INTEGER NOT NULL DEFAULT 0,
    hidden INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    guide_provider TEXT
);

-- A single airing, from whichever guide provider supplied it. Unique per
-- (channel, source_provider, start_ts) so multiple providers can coexist
-- and refresh idempotently.
CREATE TABLE IF NOT EXISTS guide_programs (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    source_provider TEXT NOT NULL,
    external_program_id TEXT,
    title TEXT NOT NULL,
    episode_title TEXT,
    season_number INTEGER,
    episode_number INTEGER,
    synopsis TEXT,
    start_ts REAL NOT NULL,
    end_ts REAL NOT NULL,
    original_air_date TEXT,
    image_url TEXT,
    is_new INTEGER NOT NULL DEFAULT 0,
    category TEXT,
    UNIQUE (channel_id, source_provider, start_ts)
);
CREATE INDEX IF NOT EXISTS idx_guide_programs_channel_start ON guide_programs (channel_id, start_ts);

-- channel_id -> XMLTV <channel id> + a display-name override, since real
-- XMLTV feeds often number channels differently than the tuner's own lineup
-- (see app.guide.xmltv).
CREATE TABLE IF NOT EXISTS xmltv_channel_map (
    channel_id TEXT PRIMARY KEY,
    xmltv_channel_id TEXT NOT NULL,
    display_name TEXT
);

-- channel_id -> Schedules Direct stationID + lineupID.
CREATE TABLE IF NOT EXISTS sd_station_map (
    channel_id TEXT PRIMARY KEY,
    station_id TEXT NOT NULL,
    lineup_id TEXT NOT NULL
);

-- Schedules Direct program metadata cache, keyed by SD's stable programID
-- (reusable across airings, unlike XMLTV which embeds full metadata
-- redundantly on every <programme>).
CREATE TABLE IF NOT EXISTS sd_program_cache (
    program_id TEXT PRIMARY KEY,
    metadata TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

-- Bookkeeping per guide provider: last refresh time, plus a cursor/etag/md5
-- string whose meaning is provider-specific (e.g. Schedules Direct's
-- schedule-md5 diffing).
CREATE TABLE IF NOT EXISTS guide_provider_state (
    provider TEXT PRIMARY KEY,
    last_refreshed_at TEXT,
    cursor TEXT
);

-- A recurring or one-shot recording instruction. `channel_id` NULL means
-- "any channel" (series rules from Schedules Direct/XMLTV without a fixed
-- home channel). `provider` names which DVRProvider owns this rule
-- ("hdhomerun_proxy" | "builtin") — see app.dvr.base.
CREATE TABLE IF NOT EXISTS recording_rules (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    series_match_key TEXT,
    channel_id TEXT,
    start_padding_seconds INTEGER NOT NULL DEFAULT 0,
    end_padding_seconds INTEGER NOT NULL DEFAULT 0,
    new_only INTEGER NOT NULL DEFAULT 1,
    priority INTEGER NOT NULL DEFAULT 0,
    max_episodes_to_keep INTEGER,
    created_at TEXT NOT NULL
);

-- One expanded, time-bound instance of a rule (or a manual one-off, with
-- rule_id NULL), produced by app.dvr.builtin.rule_expander against
-- guide_programs within its lookahead window.
CREATE TABLE IF NOT EXISTS scheduled_recordings (
    id TEXT PRIMARY KEY,
    rule_id TEXT,
    channel_id TEXT NOT NULL,
    guide_program_id TEXT,
    title TEXT NOT NULL,
    episode_title TEXT,
    season_number INTEGER,
    episode_number INTEGER,
    synopsis TEXT,
    image_url TEXT,
    original_air_date TEXT,
    category TEXT,
    start_ts REAL NOT NULL,
    end_ts REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    recording_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_scheduled_recordings_start ON scheduled_recordings (start_ts);

-- A recorded (or in-progress) file produced by the builtin DVR engine.
CREATE TABLE IF NOT EXISTS recordings (
    id TEXT PRIMARY KEY,
    scheduled_recording_id TEXT,
    title TEXT NOT NULL,
    episode_title TEXT,
    season_number INTEGER,
    episode_number INTEGER,
    synopsis TEXT,
    channel_id TEXT NOT NULL,
    channel_name_snapshot TEXT NOT NULL,
    start_ts REAL NOT NULL,
    end_ts REAL,
    original_air_date TEXT,
    category TEXT,
    file_path TEXT NOT NULL,
    file_size_bytes INTEGER,
    duration_seconds REAL,
    status TEXT NOT NULL DEFAULT 'recording',
    image_url TEXT,
    has_captions INTEGER NOT NULL DEFAULT 0,
    video_codec TEXT,
    video_width INTEGER,
    video_height INTEGER,
    audio_codec TEXT,
    audio_channels INTEGER,
    media_info TEXT
);
CREATE INDEX IF NOT EXISTS idx_recordings_start ON recordings (start_ts DESC);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # WAL lets reads (the common case here) proceed without waiting on a
    # writer, and NORMAL sync skips an fsync per commit — on the slow SD-card
    # storage a Raspberry Pi typically boots from, that's the difference
    # between a write stalling the event loop for milliseconds vs tens of
    # milliseconds. Safe here since a lost "last commit" on power loss just
    # means re-fetching from the source (guide provider, tuner) on next
    # refresh, not data corruption.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _upsert(conn: sqlite3.Connection, table: str, row: dict[str, Any], key_columns: tuple[str, ...]) -> None:
    """`INSERT INTO table (...) VALUES (...) ON CONFLICT (key_columns) DO
    UPDATE SET ...` for `row`, generically. `table` and `key_columns` are
    always caller-supplied literals (never request data), so building SQL
    via f-string here carries no injection risk.
    """
    columns = list(row.keys())
    update_columns = [c for c in columns if c not in key_columns]
    conflict_action = (
        "DO UPDATE SET " + ", ".join(f"{c} = excluded.{c}" for c in update_columns) if update_columns else "DO NOTHING"
    )
    conn.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)}) "
        f"ON CONFLICT ({', '.join(key_columns)}) {conflict_action}",
        [row[c] for c in columns],
    )


_MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS guide_programs_new (
    id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    source_provider TEXT NOT NULL,
    external_program_id TEXT,
    title TEXT NOT NULL,
    episode_title TEXT,
    season_number INTEGER,
    episode_number INTEGER,
    synopsis TEXT,
    start_ts REAL NOT NULL,
    end_ts REAL NOT NULL,
    original_air_date TEXT,
    image_url TEXT,
    is_new INTEGER NOT NULL DEFAULT 0,
    category TEXT,
    UNIQUE (channel_id, source_provider, start_ts)
);
INSERT OR IGNORE INTO guide_programs_new (
    id, channel_id, source_provider, external_program_id, title,
    episode_title, season_number, episode_number, synopsis,
    start_ts, end_ts, original_air_date, image_url, is_new, category
)
SELECT id, channel_id, source_provider, external_program_id, title,
    episode_title, season_number, episode_number, synopsis,
    start_ts, end_ts, original_air_date, image_url, is_new, category
FROM guide_programs;
DROP TABLE guide_programs;
ALTER TABLE guide_programs_new RENAME TO guide_programs;
CREATE INDEX IF NOT EXISTS idx_guide_programs_channel_start ON guide_programs (channel_id, start_ts);
"""

_MIGRATION_2 = """
ALTER TABLE recordings ADD COLUMN is_temporary INTEGER NOT NULL DEFAULT 0;
ALTER TABLE recordings ADD COLUMN last_heartbeat_at REAL;
"""


def _migration_3(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scheduled_recordings (
            id TEXT PRIMARY KEY,
            rule_id TEXT,
            channel_id TEXT NOT NULL,
            guide_program_id TEXT,
            title TEXT NOT NULL,
            episode_title TEXT,
            start_ts REAL NOT NULL,
            end_ts REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'scheduled',
            recording_id TEXT
        )
    """)
    existing_sched_cols = {row[1] for row in conn.execute("PRAGMA table_info(scheduled_recordings)").fetchall()}
    sched_cols = [
        ("season_number", "INTEGER"),
        ("episode_number", "INTEGER"),
        ("synopsis", "TEXT"),
        ("image_url", "TEXT"),
        ("original_air_date", "TEXT"),
        ("category", "TEXT"),
    ]
    for col_name, col_type in sched_cols:
        if col_name not in existing_sched_cols:
            conn.execute(f"ALTER TABLE scheduled_recordings ADD COLUMN {col_name} {col_type}")

    existing_rec_cols = {row[1] for row in conn.execute("PRAGMA table_info(recordings)").fetchall()}
    rec_cols = [
        ("synopsis", "TEXT"),
        ("original_air_date", "TEXT"),
        ("category", "TEXT"),
        ("video_codec", "TEXT"),
        ("video_width", "INTEGER"),
        ("video_height", "INTEGER"),
        ("audio_codec", "TEXT"),
        ("audio_channels", "INTEGER"),
        ("media_info", "TEXT"),
    ]
    for col_name, col_type in rec_cols:
        if col_name not in existing_rec_cols:
            conn.execute(f"ALTER TABLE recordings ADD COLUMN {col_name} {col_type}")


_MIGRATIONS: tuple[str | Callable[[sqlite3.Connection], None], ...] = (
    _MIGRATION_1,
    _MIGRATION_2,
    _migration_3,
)


def _apply_migrations(conn: sqlite3.Connection) -> None:
    """Applies each un-run migration as its own atomic unit: that migration's
    writes and its `PRAGMA user_version` bump commit (or roll back) together,
    so a crash mid-migration leaves `user_version` pointing at the last
    migration that actually completed.
    """
    conn.isolation_level = None
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    for offset, migration in enumerate(_MIGRATIONS[current_version:]):
        version = current_version + offset + 1
        if callable(migration):
            conn.execute("BEGIN")
            try:
                migration(conn)
                conn.execute(f"PRAGMA user_version = {version}")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")
        else:
            conn.executescript(f"BEGIN;\n{migration}\nPRAGMA user_version = {version};\nCOMMIT;")


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        _apply_migrations(conn)


# --- App settings / network integrations ----------------------------------


def get_app_settings() -> dict[str, str]:
    """Runtime overrides for global app config (timezone, ...), layered on
    top of the `.env`-backed `Settings` defaults — see `app.config.effective_settings`.
    """
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    return {
        row["key"]: (decrypt(row["value"]) if row["key"] in SECRET_APP_SETTINGS_KEYS else row["value"]) for row in rows
    }


def save_app_settings(overrides: dict[str, str | None]) -> None:
    """Upsert app setting overrides; a `None` value clears that key."""
    with _connect() as conn:
        for key, value in overrides.items():
            if value is None:
                conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
            else:
                stored = encrypt(value) if key in SECRET_APP_SETTINGS_KEYS else value
                _upsert(conn, "app_settings", {"key": key, "value": stored}, ("key",))


NETWORK_INTEGRATION_SECRET_KEYS = ("password", "api_key")


def _encrypt_network_integration_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {k: (encrypt(v) if k in NETWORK_INTEGRATION_SECRET_KEYS and v else v) for k, v in settings.items()}


def _decrypt_network_integration_settings(settings: dict[str, Any]) -> dict[str, Any]:
    return {k: (decrypt(v) if k in NETWORK_INTEGRATION_SECRET_KEYS and v else v) for k, v in settings.items()}


def save_network_integration(id: str, type_: str, name: str, settings: dict[str, Any]) -> None:
    """Create or overwrite a network integration row (its full settings, not a partial merge — callers merge first)."""
    stored = _encrypt_network_integration_settings(settings)
    with _connect() as conn:
        _upsert(
            conn,
            "network_integrations",
            {"id": id, "type": type_, "name": name, "settings": json.dumps(stored)},
            ("id",),
        )


def get_network_integration(id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT id, type, name, settings FROM network_integrations WHERE id = ?", (id,)).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "type": row["type"],
        "name": row["name"],
        "settings": _decrypt_network_integration_settings(json.loads(row["settings"])),
    }


def list_network_integrations(type_: str | None = None) -> list[dict[str, Any]]:
    with _connect() as conn:
        if type_ is None:
            rows = conn.execute("SELECT id, type, name, settings FROM network_integrations").fetchall()
        else:
            rows = conn.execute(
                "SELECT id, type, name, settings FROM network_integrations WHERE type = ?", (type_,)
            ).fetchall()
    return [
        {
            "id": row["id"],
            "type": row["type"],
            "name": row["name"],
            "settings": _decrypt_network_integration_settings(json.loads(row["settings"])),
        }
        for row in rows
    ]


def delete_network_integration(id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM network_integrations WHERE id = ?", (id,))


# --- Users, devices, sessions, preferences, tokens -------------------------
#
# No FK constraints here (no table in `_SCHEMA` uses one, and `_connect()`
# never sets `PRAGMA foreign_keys=ON`). Cascades on delete are driven by the
# two registries below instead of a hand-written DELETE per table.

_USER_SCOPED_TABLES: tuple[tuple[str, str], ...] = (
    ("sessions", "user_id"),
    ("auth_tokens", "user_id"),
    ("user_preferences", "user_id"),
)

_DEVICE_SCOPED_TABLES: tuple[tuple[str, str], ...] = (
    ("sessions", "device_id"),
    ("auth_tokens", "device_id"),
)


def create_user(
    id: str,
    name: str,
    avatar: str | None,
    pin_hash: str | None,
    pin_salt: str | None,
    pin_iterations: int | None,
    created_at: str,
    role: str = "member",
) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO users (id, name, avatar, pin_hash, pin_salt, pin_iterations, created_at, role) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (id, name, avatar, pin_hash, pin_salt, pin_iterations, created_at, role),
        )


def get_user(user_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return None if row is None else dict(row)


def list_users() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at ASC").fetchall()
    return [dict(row) for row in rows]


def update_user(user_id: str, **fields: Any) -> None:
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE users SET {columns} WHERE id = ?", (*fields.values(), user_id))


def delete_user(user_id: str) -> None:
    with _connect() as conn:
        for table, column in _USER_SCOPED_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))


def create_device(id: str, name: str, created_at: str, last_seen_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO devices (id, name, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
            (id, name, created_at, last_seen_at),
        )


def get_device(device_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return None if row is None else dict(row)


def list_devices() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM devices ORDER BY created_at ASC").fetchall()
    return [dict(row) for row in rows]


def update_device(device_id: str, **fields: Any) -> None:
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE devices SET {columns} WHERE id = ?", (*fields.values(), device_id))


def touch_device(device_id: str, last_seen_at: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE devices SET last_seen_at = ? WHERE id = ?", (last_seen_at, device_id))


def delete_device(device_id: str) -> None:
    with _connect() as conn:
        for table, column in _DEVICE_SCOPED_TABLES:
            conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (device_id,))
        conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))


def create_session(id: str, user_id: str, device_id: str, created_at: str, expires_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sessions (id, user_id, device_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (id, user_id, device_id, created_at, expires_at),
        )


def get_session(session_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    return None if row is None else dict(row)


def delete_session(session_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


def delete_sessions_for_user(user_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def delete_sessions_for_device(device_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE device_id = ?", (device_id,))


def delete_expired_sessions(now: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))


# Bearer tokens for native clients — see the auth_tokens table comment above.
# The raw token is generated by the caller (app.auth.new_token()) and shown
# to the user exactly once, at issuance; only its hash is ever persisted.


def create_auth_token(id: str, user_id: str, device_id: str, token_hash: str, name: str, created_at: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO auth_tokens (id, user_id, device_id, token_hash, name, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (id, user_id, device_id, token_hash, name, created_at),
        )


def get_auth_token_by_hash(token_hash: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM auth_tokens WHERE token_hash = ? AND revoked_at IS NULL", (token_hash,)
        ).fetchone()
    return None if row is None else dict(row)


def touch_auth_token(token_id: str, last_used_at: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE auth_tokens SET last_used_at = ? WHERE id = ?", (last_used_at, token_id))


def list_auth_tokens(user_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM auth_tokens WHERE user_id = ? AND revoked_at IS NULL ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def revoke_auth_token(token_id: str, revoked_at: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE auth_tokens SET revoked_at = ? WHERE id = ?", (revoked_at, token_id))


_DEFAULT_PREFERENCES: dict[str, Any] = {
    "theme": "dark",
    "locale": "en",
}


def get_user_preferences(user_id: str) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT preferences FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
    overrides = json.loads(row["preferences"]) if row else {}
    return {**_DEFAULT_PREFERENCES, **overrides}


def save_user_preferences(user_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
    """Merge `overrides` onto the user's stored preferences and persist the result."""
    merged = {**get_user_preferences(user_id), **overrides}
    with _connect() as conn:
        _upsert(conn, "user_preferences", {"user_id": user_id, "preferences": json.dumps(merged)}, ("user_id",))
    return merged


# --- Channels / guide --------------------------------------------------


def upsert_channel(id: str, channel_number: str, name: str, is_hd: bool, sort_order: int = 0) -> None:
    """Create the channel if new; on an existing id, only refresh the
    tuner-sourced fields (number/name/HD flag) and leave user-editable
    fields (favorite, hidden, sort_order, guide_provider) untouched."""
    with _connect() as conn:
        existing = conn.execute("SELECT 1 FROM channels WHERE id = ?", (id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE channels SET channel_number = ?, name = ?, is_hd = ? WHERE id = ?",
                (channel_number, name, int(is_hd), id),
            )
        else:
            conn.execute(
                "INSERT INTO channels "
                "(id, channel_number, name, is_hd, is_favorite, hidden, sort_order, guide_provider) "
                "VALUES (?, ?, ?, ?, 0, 0, ?, NULL)",
                (id, channel_number, name, int(is_hd), sort_order),
            )


def list_channels(include_hidden: bool = False) -> list[dict[str, Any]]:
    with _connect() as conn:
        if include_hidden:
            rows = conn.execute("SELECT * FROM channels ORDER BY sort_order, channel_number").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM channels WHERE hidden = 0 ORDER BY sort_order, channel_number"
            ).fetchall()
    return [dict(row) for row in rows]


def get_channel(channel_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    return None if row is None else dict(row)


def get_channel_by_number(channel_number: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM channels WHERE channel_number = ?", (channel_number,)).fetchone()
    return None if row is None else dict(row)


def update_channel(channel_id: str, **fields: Any) -> None:
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE channels SET {columns} WHERE id = ?", (*fields.values(), channel_id))


def upsert_guide_programs(programs: list[dict[str, Any]]) -> None:
    """Bulk-upsert a guide provider's refresh result, keyed by (channel_id, source_provider, start_ts)."""
    if not programs:
        return
    with _connect() as conn:
        for program in programs:
            row = {**program, "id": program.get("id") or uuid.uuid4().hex}
            _upsert(conn, "guide_programs", row, ("channel_id", "source_provider", "start_ts"))


def list_guide_programs(channel_ids: list[str], start_ts: float, end_ts: float) -> list[dict[str, Any]]:
    if not channel_ids:
        return []
    placeholders = ", ".join("?" for _ in channel_ids)
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM guide_programs WHERE channel_id IN ({placeholders}) "
            "AND start_ts < ? AND end_ts > ? ORDER BY channel_id, start_ts",
            (*channel_ids, end_ts, start_ts),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_future_guide_programs(channel_id: str, source_provider: str, after_ts: float) -> None:
    """Used by providers with no incremental API to full-replace a channel's upcoming grid per refresh."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM guide_programs WHERE channel_id = ? AND source_provider = ? AND start_ts >= ?",
            (channel_id, source_provider, after_ts),
        )


def delete_guide_programs_by_provider(source_provider: str) -> None:
    """Delete all guide programs for a given provider (e.g. on full XMLTV feed reload)."""
    with _connect() as conn:
        conn.execute("DELETE FROM guide_programs WHERE source_provider = ?", (source_provider,))


def get_guide_provider_state(provider: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM guide_provider_state WHERE provider = ?", (provider,)).fetchone()
    return None if row is None else dict(row)


def save_guide_provider_state(provider: str, last_refreshed_at: str, cursor: str | None = None) -> None:
    with _connect() as conn:
        _upsert(
            conn,
            "guide_provider_state",
            {"provider": provider, "last_refreshed_at": last_refreshed_at, "cursor": cursor},
            ("provider",),
        )


def get_xmltv_guide_stats() -> dict[str, Any]:
    with _connect() as conn:
        state_row = conn.execute(
            "SELECT last_refreshed_at, cursor FROM guide_provider_state WHERE provider = 'xmltv'"
        ).fetchone()

        programs_row = conn.execute(
            "SELECT COUNT(*) AS total_programs, "
            "COUNT(DISTINCT channel_id) AS channels_with_programs, "
            "MIN(start_ts) AS min_start_ts, "
            "MAX(end_ts) AS max_end_ts "
            "FROM guide_programs WHERE source_provider = 'xmltv'"
        ).fetchone()

        map_row = conn.execute("SELECT COUNT(*) AS total_mapped FROM xmltv_channel_map").fetchone()

        net_row = conn.execute("SELECT settings FROM network_integrations WHERE type = 'xmltv'").fetchone()

    url = None
    if net_row and net_row["settings"]:
        try:
            settings_dict = json.loads(net_row["settings"])
            url = settings_dict.get("url")
        except Exception:
            pass

    last_refreshed_at = state_row["last_refreshed_at"] if state_row else None
    cursor_str = state_row["cursor"] if state_row else None
    channels_in_feed = 0
    if cursor_str:
        try:
            cursor_data = json.loads(cursor_str)
            channels_in_feed = int(cursor_data.get("channels_in_feed", 0))
        except Exception:
            pass

    total_programs = int(programs_row["total_programs"]) if programs_row else 0
    channels_with_programs = int(programs_row["channels_with_programs"]) if programs_row else 0
    min_start_ts = programs_row["min_start_ts"] if programs_row and programs_row["min_start_ts"] is not None else None
    max_end_ts = programs_row["max_end_ts"] if programs_row and programs_row["max_end_ts"] is not None else None
    mapped_channels_count = int(map_row["total_mapped"]) if map_row else 0

    days_count = 0.0
    start_date = None
    end_date = None
    if min_start_ts is not None and max_end_ts is not None and max_end_ts > min_start_ts:
        days_count = round((max_end_ts - min_start_ts) / 86400.0, 1)
        start_date = datetime.fromtimestamp(min_start_ts, tz=UTC).isoformat()
        end_date = datetime.fromtimestamp(max_end_ts, tz=UTC).isoformat()

    return {
        "url": url,
        "last_refreshed_at": last_refreshed_at,
        "channels_in_feed": channels_in_feed,
        "mapped_channels_count": mapped_channels_count,
        "channels_with_programs": channels_with_programs,
        "programs_count": total_programs,
        "days_count": days_count,
        "start_date": start_date,
        "end_date": end_date,
        "start_ts": min_start_ts,
        "end_ts": max_end_ts,
    }


def upsert_xmltv_channel_map(channel_id: str, xmltv_channel_id: str, display_name: str | None) -> None:
    with _connect() as conn:
        _upsert(
            conn,
            "xmltv_channel_map",
            {"channel_id": channel_id, "xmltv_channel_id": xmltv_channel_id, "display_name": display_name},
            ("channel_id",),
        )


def get_xmltv_channel_map(channel_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM xmltv_channel_map WHERE channel_id = ?", (channel_id,)).fetchone()
    return None if row is None else dict(row)


def list_xmltv_channel_map() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM xmltv_channel_map").fetchall()
    return [dict(row) for row in rows]


def delete_xmltv_channel_map(channel_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM xmltv_channel_map WHERE channel_id = ?", (channel_id,))


def upsert_sd_station_map(channel_id: str, station_id: str, lineup_id: str) -> None:
    with _connect() as conn:
        _upsert(
            conn,
            "sd_station_map",
            {"channel_id": channel_id, "station_id": station_id, "lineup_id": lineup_id},
            ("channel_id",),
        )


def get_sd_station_map(channel_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM sd_station_map WHERE channel_id = ?", (channel_id,)).fetchone()
    return None if row is None else dict(row)


def list_sd_station_map() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM sd_station_map").fetchall()
    return [dict(row) for row in rows]


def delete_sd_station_map(channel_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sd_station_map WHERE channel_id = ?", (channel_id,))


def upsert_sd_program_cache(programs: list[dict[str, Any]]) -> None:
    with _connect() as conn:
        for p in programs:
            metadata_str = p["metadata"] if isinstance(p["metadata"], str) else json.dumps(p["metadata"])
            _upsert(
                conn,
                "sd_program_cache",
                {"program_id": p["program_id"], "metadata": metadata_str, "fetched_at": p["fetched_at"]},
                ("program_id",),
            )


def get_cached_sd_programs(program_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not program_ids:
        return {}
    result: dict[str, dict[str, Any]] = {}
    with _connect() as conn:
        placeholders = ",".join("?" for _ in program_ids)
        rows = conn.execute(
            f"SELECT program_id, metadata, fetched_at FROM sd_program_cache WHERE program_id IN ({placeholders})",
            program_ids,
        ).fetchall()
        for r in rows:
            try:
                meta = json.loads(r["metadata"])
            except Exception:
                meta = {}
            result[r["program_id"]] = {"program_id": r["program_id"], "metadata": meta, "fetched_at": r["fetched_at"]}
    return result


def delete_expired_sd_program_cache(before_iso: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sd_program_cache WHERE fetched_at < ?", (before_iso,))


DEFAULT_GUIDE_PROVIDER_PRIORITY: tuple[str, ...] = ("xmltv", "schedules_direct", "hdhomerun_cloud")


def resolve_guide_programs(
    channels: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    default_priority: tuple[str, ...] = DEFAULT_GUIDE_PROVIDER_PRIORITY,
) -> dict[str, list[dict[str, Any]]]:
    """Collapse list_guide_programs()'s unfiltered, possibly multi-provider
    rows down to one effective list of guide airings per channel.
    Higher-priority provider airings take precedence, and any gaps (such as
    missing current or earlier airings) are filled in from lower-priority
    providers."""
    by_channel_and_provider: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        by_channel_and_provider.setdefault(row["channel_id"], {}).setdefault(row["source_provider"], []).append(row)

    result: dict[str, list[dict[str, Any]]] = {}
    for channel in channels:
        by_provider = by_channel_and_provider.get(channel["id"])
        if not by_provider:
            continue
        pinned = channel.get("guide_provider")
        priority = ([pinned] if pinned else []) + [p for p in default_priority if p != pinned]

        merged_rows: list[dict[str, Any]] = []
        for provider in priority:
            provider_rows = by_provider.get(provider)
            if not provider_rows:
                continue
            if not merged_rows:
                merged_rows.extend(provider_rows)
            else:
                for candidate in provider_rows:
                    c_start = candidate.get("start_ts")
                    c_end = candidate.get("end_ts")
                    if c_start is None or c_end is None or c_end <= c_start:
                        continue
                    overlaps = any(
                        (r.get("start_ts") < c_end and r.get("end_ts") > c_start)
                        for r in merged_rows
                        if r.get("start_ts") is not None and r.get("end_ts") is not None
                    )
                    if not overlaps:
                        merged_rows.append(candidate)

        if merged_rows:
            result[channel["id"]] = sorted(merged_rows, key=lambda r: r["start_ts"])
    return result


# --- Recording rules / scheduled recordings / recordings -------------------


def create_recording_rule(rule: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO recording_rules (id, provider, type, title, series_match_key, channel_id, "
            "start_padding_seconds, end_padding_seconds, new_only, priority, max_episodes_to_keep, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rule["id"],
                rule["provider"],
                rule["type"],
                rule["title"],
                rule.get("series_match_key"),
                rule.get("channel_id"),
                rule.get("start_padding_seconds", 0),
                rule.get("end_padding_seconds", 0),
                int(rule.get("new_only", True)),
                rule.get("priority", 0),
                rule.get("max_episodes_to_keep"),
                rule.get("created_at") or datetime.now(UTC).isoformat(),
            ),
        )


def list_recording_rules(provider: str | None = None) -> list[dict[str, Any]]:
    with _connect() as conn:
        if provider is None:
            rows = conn.execute("SELECT * FROM recording_rules ORDER BY created_at").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM recording_rules WHERE provider = ? ORDER BY created_at", (provider,)
            ).fetchall()
    return [dict(row) for row in rows]


def get_recording_rule(rule_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM recording_rules WHERE id = ?", (rule_id,)).fetchone()
    return None if row is None else dict(row)


def delete_recording_rule(rule_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM recording_rules WHERE id = ?", (rule_id,))


def upsert_scheduled_recording(scheduled: dict[str, Any]) -> None:
    with _connect() as conn:
        _upsert(conn, "scheduled_recordings", scheduled, ("id",))


def list_scheduled_recordings(status: str | None = None) -> list[dict[str, Any]]:
    with _connect() as conn:
        if status is None:
            rows = conn.execute("SELECT * FROM scheduled_recordings ORDER BY start_ts").fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM scheduled_recordings WHERE status = ? ORDER BY start_ts", (status,)
            ).fetchall()
    return [dict(row) for row in rows]


def delete_scheduled_recordings_for_rule(rule_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM scheduled_recordings WHERE rule_id = ? AND status = 'scheduled'", (rule_id,))


def create_recording(recording: dict[str, Any]) -> None:
    with _connect() as conn:
        _upsert(conn, "recordings", recording, ("id",))


def update_recording(recording_id: str, **fields: Any) -> None:
    if not fields:
        return
    columns = ", ".join(f"{key} = ?" for key in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE recordings SET {columns} WHERE id = ?", (*fields.values(), recording_id))


def list_recordings() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM recordings ORDER BY start_ts DESC").fetchall()
    return [dict(row) for row in rows]


def get_recording(recording_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    return None if row is None else dict(row)


def delete_recording(recording_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
