from __future__ import annotations

import sqlite3

from app.storage import db


def test_fresh_install_ends_with_zero_users_and_zero_admins(tmp_db):
    assert db.list_users() == []


def test_fresh_install_users_table_has_a_role_column(tmp_db):
    db.create_user("alice", "Alice", None, None, None, None, "2026-01-01T00:00:00Z")

    assert db.get_user("alice")["role"] == "member"


def test_fresh_install_sets_user_version_to_latest(tmp_db):
    with sqlite3.connect(tmp_db) as conn:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == len(db._MIGRATIONS)


def test_init_db_is_idempotent(tmp_db):
    db.create_user("alice", "Alice", None, None, None, None, "2026-01-01T00:00:00Z")

    db.init_db()

    assert db.get_user("alice") is not None


def test_migration_1_allows_multi_provider_coexistence(tmp_path, monkeypatch):
    test_db = tmp_path / "migration_test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)

    # Setup database with old schema (user_version = 0 and UNIQUE (channel_id, start_ts))
    with sqlite3.connect(test_db) as conn:
        conn.executescript("""
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                avatar TEXT,
                pin_hash TEXT,
                pin_salt TEXT,
                pin_iterations INTEGER,
                created_at TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member'
            );
            CREATE TABLE guide_programs (
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
                UNIQUE (channel_id, start_ts)
            );
            INSERT INTO guide_programs (id, channel_id, source_provider, title, start_ts, end_ts)
            VALUES ('p1', 'c1', 'hdhomerun_cloud', 'Old Show', 1000.0, 2000.0);
            CREATE TABLE recording_rules (
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
            CREATE TABLE recordings (
                id TEXT PRIMARY KEY,
                scheduled_recording_id TEXT,
                title TEXT NOT NULL,
                episode_title TEXT,
                season_number INTEGER,
                episode_number INTEGER,
                channel_id TEXT NOT NULL,
                channel_name_snapshot TEXT NOT NULL,
                start_ts REAL NOT NULL,
                end_ts REAL,
                file_path TEXT NOT NULL,
                file_size_bytes INTEGER,
                duration_seconds REAL,
                status TEXT NOT NULL DEFAULT 'recording',
                image_url TEXT,
                has_captions INTEGER NOT NULL DEFAULT 0
            );
            PRAGMA user_version = 0;
        """)

    # Run migrations
    with sqlite3.connect(test_db) as conn:
        db._apply_migrations(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == len(db._MIGRATIONS)

    # Verify both providers can now exist for same channel and start_ts
    db.upsert_guide_programs([
        {
            "id": "p2",
            "channel_id": "c1",
            "source_provider": "xmltv",
            "title": "XMLTV Show",
            "start_ts": 1000.0,
            "end_ts": 2000.0,
        }
    ])

    programs = db.list_guide_programs(["c1"], 0, 5000)
    assert len(programs) == 2
    providers = {p["source_provider"] for p in programs}
    assert providers == {"hdhomerun_cloud", "xmltv"}


def test_migration_3_adds_metadata_columns(tmp_path, monkeypatch):
    test_db = tmp_path / "migration3_test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)

    with sqlite3.connect(test_db) as conn:
        conn.executescript("""
            CREATE TABLE recording_rules (
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
            CREATE TABLE scheduled_recordings (
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
            );
            CREATE TABLE recordings (
                id TEXT PRIMARY KEY,
                scheduled_recording_id TEXT,
                title TEXT NOT NULL,
                episode_title TEXT,
                season_number INTEGER,
                episode_number INTEGER,
                channel_id TEXT NOT NULL,
                channel_name_snapshot TEXT NOT NULL,
                start_ts REAL NOT NULL,
                end_ts REAL,
                file_path TEXT NOT NULL,
                file_size_bytes INTEGER,
                duration_seconds REAL,
                status TEXT NOT NULL DEFAULT 'recording',
                image_url TEXT,
                has_captions INTEGER NOT NULL DEFAULT 0,
                is_temporary INTEGER NOT NULL DEFAULT 0,
                last_heartbeat_at REAL
            );
            PRAGMA user_version = 2;
        """)

    with sqlite3.connect(test_db) as conn:
        db._apply_migrations(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == len(db._MIGRATIONS)

        rec_cols = {row[1] for row in conn.execute("PRAGMA table_info(recordings)").fetchall()}
        assert "synopsis" in rec_cols
        assert "video_codec" in rec_cols
        assert "video_width" in rec_cols
        assert "video_height" in rec_cols
        assert "audio_codec" in rec_cols
        assert "audio_channels" in rec_cols
        assert "media_info" in rec_cols
        assert "original_air_date" in rec_cols
        assert "category" in rec_cols

        sched_cols = {row[1] for row in conn.execute("PRAGMA table_info(scheduled_recordings)").fetchall()}
        assert "synopsis" in sched_cols
        assert "image_url" in sched_cols
        assert "season_number" in sched_cols
        assert "episode_number" in sched_cols
        assert "original_air_date" in sched_cols
        assert "category" in sched_cols


def test_migration_4_adds_status_title_index(tmp_path, monkeypatch):
    test_db = tmp_path / "migration4_test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)

    with sqlite3.connect(test_db) as conn:
        conn.executescript("""
            CREATE TABLE recording_rules (
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
            CREATE TABLE recordings (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                channel_name_snapshot TEXT NOT NULL,
                start_ts REAL NOT NULL,
                end_ts REAL,
                file_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'recording'
            );
            CREATE INDEX idx_recordings_status ON recordings (status);
            PRAGMA user_version = 3;
        """)

    with sqlite3.connect(test_db) as conn:
        db._apply_migrations(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == len(db._MIGRATIONS)

        index_names = {row[1] for row in conn.execute("PRAGMA index_list(recordings)").fetchall()}
        assert "idx_recordings_status_title" in index_names


def test_migration_7_drops_devices_and_device_id_columns(tmp_path, monkeypatch):
    test_db = tmp_path / "migration7_test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)

    with sqlite3.connect(test_db) as conn:
        conn.executescript("""
            CREATE TABLE devices (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL
            );
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE INDEX idx_sessions_device_id ON sessions (device_id);
            CREATE TABLE auth_tokens (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used_at TEXT,
                revoked_at TEXT
            );
            INSERT INTO devices (id, name, created_at, last_seen_at)
            VALUES ('dev1', 'Kitchen Tablet', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z');
            PRAGMA user_version = 6;
        """)

    with sqlite3.connect(test_db) as conn:
        db._apply_migrations(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == len(db._MIGRATIONS)

        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "devices" not in tables

        session_cols = {row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
        assert "device_id" not in session_cols

        token_cols = {row[1] for row in conn.execute("PRAGMA table_info(auth_tokens)").fetchall()}
        assert "device_id" not in token_cols
