"""Shared SQLite connection/schema/migration machinery for the app.storage.db
submodules. Not meant to be imported directly outside this package — see
app/storage/db/__init__.py for the public, re-exported API.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from app.config import DB_PATH

# Re-exported by __init__.py as the package's own attribute, which is what
# `monkeypatch.setattr(db, "DB_PATH", ...)` (see tests/conftest.py's tmp_db
# fixture) actually patches. `_connect()` below reads it back through the
# package rather than this module-local copy, so the patch takes effect.
DB_PATH = DB_PATH

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

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions (user_id);

-- Bearer tokens for native clients (iOS/tvOS/Android/Android TV/Fire TV),
-- issued alongside a session cookie at login. A system media pipeline
-- (AVPlayer/ExoPlayer) handed a raw stream URL doesn't reliably thread an
-- app's cookie jar the way a browser fetch does, and per-token revocation
-- ("remove this Apple TV") is a single row delete instead of hunting down a
-- shared cookie. Only `token_hash` is stored — the raw token is shown once,
-- at issuance, the same way a PIN's hash/salt work in `users` above.
CREATE TABLE IF NOT EXISTS auth_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
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
    audio TEXT,
    has_subtitles INTEGER NOT NULL DEFAULT 1,
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
CREATE INDEX IF NOT EXISTS idx_recording_rules_provider ON recording_rules (provider);

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
CREATE INDEX IF NOT EXISTS idx_scheduled_recordings_rule_id ON scheduled_recordings (rule_id);

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
CREATE INDEX IF NOT EXISTS idx_recordings_status ON recordings (status);
CREATE INDEX IF NOT EXISTS idx_recordings_status_title ON recordings (status, LOWER(TRIM(title)));
"""


def _validate_update_columns(table: str, allowed: frozenset[str], fields: dict[str, Any]) -> None:
    unknown = fields.keys() - allowed
    if unknown:
        raise ValueError(f"Refusing to update unknown column(s) on {table}: {sorted(unknown)}")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    from app.storage import db as _db

    conn = sqlite3.connect(_db.DB_PATH)
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
    try:
        with conn:
            yield conn
    finally:
        conn.close()


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


_MIGRATION_4 = """
CREATE INDEX IF NOT EXISTS idx_recordings_status_title ON recordings (status, LOWER(TRIM(title)));
"""


_MIGRATION_5 = """
CREATE TABLE IF NOT EXISTS job_runs (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    error TEXT
);
CREATE INDEX IF NOT EXISTS idx_job_runs_job_id_started_at ON job_runs (job_id, started_at);
"""


_MIGRATION_6 = """
ALTER TABLE recording_rules ADD COLUMN title_match_mode TEXT NOT NULL DEFAULT 'exact';
ALTER TABLE recording_rules ADD COLUMN keyword_query TEXT;
"""


# Removes the `devices` entity: sessions and auth_tokens were only ever
# grouped under a device for bulk ("forget this browser") revocation, which
# turned out not to be worth the extra entity/cookie/registration round-trip
# — see app.auth and app.api.users for the per-session/per-token model this
# leaves behind. Guarded column checks because a fresh install's _SCHEMA
# above never had `device_id` in the first place — only a pre-existing DB
# upgrading through this migration does.
def _migration_7(conn: sqlite3.Connection) -> None:
    session_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "device_id" in session_cols:
        conn.execute("DROP INDEX IF EXISTS idx_sessions_device_id")
        conn.execute("ALTER TABLE sessions DROP COLUMN device_id")

    token_cols = {row[1] for row in conn.execute("PRAGMA table_info(auth_tokens)").fetchall()}
    if "device_id" in token_cols:
        conn.execute("ALTER TABLE auth_tokens DROP COLUMN device_id")

    conn.execute("DROP TABLE IF EXISTS devices")


def _migration_8(conn: sqlite3.Connection) -> None:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if "guide_programs" in tables:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(guide_programs)").fetchall()}
        if "audio" not in cols:
            conn.execute("ALTER TABLE guide_programs ADD COLUMN audio TEXT")
        if "has_subtitles" not in cols:
            conn.execute("ALTER TABLE guide_programs ADD COLUMN has_subtitles INTEGER NOT NULL DEFAULT 1")


_MIGRATIONS: tuple[str | Callable[[sqlite3.Connection], None], ...] = (
    _MIGRATION_1,
    _MIGRATION_2,
    _migration_3,
    _MIGRATION_4,
    _MIGRATION_5,
    _MIGRATION_6,
    _migration_7,
    _migration_8,
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
