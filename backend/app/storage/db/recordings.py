"""Recording rules, their expanded scheduled-recording instances, and the
recorded (or in-progress) files produced from them by the builtin DVR.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.storage.db.connection import _connect, _upsert, _validate_update_columns

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
    }
)


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


def update_recording(recording_id: str, **fields: Any) -> None:
    if not fields:
        return
    _validate_update_columns("recordings", _RECORDING_UPDATABLE_COLUMNS, fields)
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
