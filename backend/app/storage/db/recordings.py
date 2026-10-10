"""Recording rules, their expanded scheduled-recording instances, and the
recorded (or in-progress) files produced from them by the builtin DVR.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.storage.cache import cache
from app.storage.db.connection import _connect, _upsert, _validate_update_columns

_RECORDINGS_CACHE_PREFIX = "dvr_recordings:"

_RECORDING_UPDATABLE_COLUMNS = frozenset(
    {
        "scheduled_recording_id",
        "title",
        "episode_title",
        "season_number",
        "episode_number",
        "synopsis",
        "channel_id",
        "channel_name_snapshot",
        "start_ts",
        "end_ts",
        "original_air_date",
        "category",
        "file_path",
        "file_size_bytes",
        "duration_seconds",
        "status",
        "image_url",
        "has_captions",
        "video_codec",
        "video_width",
        "video_height",
        "audio_codec",
        "audio_channels",
        "media_info",
        "is_temporary",
        "last_heartbeat_at",
        "comskip_status",
        "comskip_attempts",
    }
)

_RECORDING_RULE_UPDATABLE_COLUMNS = frozenset(
    {
        "title",
        "series_match_key",
        "channel_id",
        "start_padding_seconds",
        "end_padding_seconds",
        "new_only",
        "priority",
        "max_episodes_to_keep",
        "title_match_mode",
        "keyword_query",
        "fallback_reason",
        "comskip_override",
    }
)


def create_recording_rule(rule: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO recording_rules (id, provider, type, title, series_match_key, channel_id, "
            "start_padding_seconds, end_padding_seconds, new_only, priority, max_episodes_to_keep, "
            "title_match_mode, keyword_query, fallback_reason, comskip_override, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                rule.get("title_match_mode") or "exact",
                rule.get("keyword_query"),
                rule.get("fallback_reason"),
                rule.get("comskip_override") or "default",
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


def update_recording_rule(rule_id: str, **fields: Any) -> None:
    if not fields:
        return
    _validate_update_columns("recording_rules", _RECORDING_RULE_UPDATABLE_COLUMNS, fields)
    columns = ", ".join(f"{key} = ?" for key in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE recording_rules SET {columns} WHERE id = ?", (*fields.values(), rule_id))


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


def mark_scheduled_recording_in_progress(scheduled_id: str, recording_id: str) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE scheduled_recordings SET status = 'in_progress', recording_id = ? WHERE id = ?",
            (recording_id, scheduled_id),
        )


def update_scheduled_recording_status(scheduled_id: str, status: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE scheduled_recordings SET status = ? WHERE id = ?", (status, scheduled_id))


def mark_in_progress_scheduled_recordings_interrupted() -> None:
    with _connect() as conn:
        conn.execute("UPDATE scheduled_recordings SET status = 'interrupted' WHERE status = 'in_progress'")


def create_recording(recording: dict[str, Any]) -> None:
    with _connect() as conn:
        _upsert(conn, "recordings", recording, ("id",))
    cache.delete_prefix(_RECORDINGS_CACHE_PREFIX)


def update_recording(recording_id: str, **fields: Any) -> None:
    if not fields:
        return
    _validate_update_columns("recordings", _RECORDING_UPDATABLE_COLUMNS, fields)
    columns = ", ".join(f"{key} = ?" for key in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE recordings SET {columns} WHERE id = ?", (*fields.values(), recording_id))
    # Watch-session heartbeats update only this field on every tick (see
    # app/dvr/builtin/watch.py), and it never affects search/listing output,
    # so invalidating on it would thrash the cache for anyone else browsing
    # recordings while a recording is being actively watched.
    if set(fields.keys()) != {"last_heartbeat_at"}:
        cache.delete_prefix(_RECORDINGS_CACHE_PREFIX)


def _escape_like(term: str) -> str:
    """Escape SQLite LIKE wildcards so a literal '%'/'_' in user input can't
    act as one; paired with `ESCAPE '\\'` in the calling query.
    """
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_recordings(
    *, search: str | None = None, limit: int | None = None, offset: int = 0
) -> list[dict[str, Any]]:
    """Like `list_recordings()`, optionally filtered by a case-insensitive
    substring match against title/episode_title/synopsis/category/channel
    name, with true SQL-level LIMIT/OFFSET pagination.
    """
    query = "SELECT * FROM recordings"
    params: list[Any] = []
    if search:
        pattern = f"%{_escape_like(search)}%"
        query += (
            " WHERE title LIKE ? ESCAPE '\\'"
            " OR episode_title LIKE ? ESCAPE '\\'"
            " OR synopsis LIKE ? ESCAPE '\\'"
            " OR category LIKE ? ESCAPE '\\'"
            " OR channel_name_snapshot LIKE ? ESCAPE '\\'"
        )
        params.extend([pattern] * 5)
    query += " ORDER BY start_ts DESC"
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])
    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def list_recordings() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM recordings ORDER BY start_ts DESC").fetchall()
    return [dict(row) for row in rows]


def list_completed_recordings() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM recordings WHERE status = 'completed' ORDER BY start_ts ASC").fetchall()
    return [dict(row) for row in rows]


def list_completed_recordings_by_title(normalized_title: str) -> list[dict[str, Any]]:
    """`normalized_title` must already be trimmed/lowercased by the caller
    (matches `LOWER(TRIM(title))`, backed by idx_recordings_status_title).
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM recordings WHERE status = 'completed' AND LOWER(TRIM(title)) = ? ORDER BY start_ts ASC",
            (normalized_title,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_recording(recording_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    return None if row is None else dict(row)


def get_comskip_override_for_recording(recording_id: str) -> str:
    """'default'|'always'|'never' from the recording_rule that produced
    recording_id, or 'default' for a manual/one-off recording.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT rr.comskip_override FROM recordings r "
            "JOIN scheduled_recordings sr ON sr.id = r.scheduled_recording_id "
            "JOIN recording_rules rr ON rr.id = sr.rule_id "
            "WHERE r.id = ?",
            (recording_id,),
        ).fetchone()
    return row[0] if row else "default"


def delete_recording(recording_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM recordings WHERE id = ?", (recording_id,))
    cache.delete_prefix(_RECORDINGS_CACHE_PREFIX)


def get_hdhomerun_comskip_status(recording_id: str) -> dict[str, Any] | None:
    """Comskip status/attempts tracked for a HDHomeRun-DVR recording - these
    have no row in `recordings` (see `hdhomerun_comskip_status`'s own
    comment in the schema), so they're tracked in this separate table
    instead, keyed by the HDHomeRun engine's own recording ID.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM hdhomerun_comskip_status WHERE recording_id = ?", (recording_id,)
        ).fetchone()
    return None if row is None else dict(row)


def upsert_hdhomerun_comskip_status(recording_id: str, filename: str, status: str, attempts: int) -> None:
    with _connect() as conn:
        _upsert(
            conn,
            "hdhomerun_comskip_status",
            {
                "recording_id": recording_id,
                "filename": filename,
                "status": status,
                "attempts": attempts,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            key_columns=("recording_id",),
        )
