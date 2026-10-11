"""Sports auto-recording: favorited teams/leagues, the broadcast-network to
local-channel map, and ESPN-event-to-recording-rule tracking (see
app.dvr.builtin.sports_autorecord).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.storage.db.connection import _connect, _upsert


def create_sports_favorite(favorite: dict[str, Any]) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sports_favorites (id, kind, league, espn_team_id, team_display_name, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                favorite["id"],
                favorite.get("kind", "team"),
                favorite["league"],
                favorite.get("espn_team_id"),
                favorite.get("team_display_name"),
                int(favorite.get("enabled", True)),
                favorite.get("created_at") or datetime.now(UTC).isoformat(),
            ),
        )


def list_sports_favorites() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM sports_favorites ORDER BY created_at").fetchall()
    return [dict(row) for row in rows]


def get_sports_favorite(favorite_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM sports_favorites WHERE id = ?", (favorite_id,)).fetchone()
    return None if row is None else dict(row)


def update_sports_favorite(favorite_id: str, **fields: Any) -> None:
    if not fields:
        return
    allowed = {"enabled"}
    if not set(fields) <= allowed:
        raise ValueError(f"Unsupported sports_favorites columns: {set(fields) - allowed}")
    columns = ", ".join(f"{key} = ?" for key in fields)
    with _connect() as conn:
        conn.execute(f"UPDATE sports_favorites SET {columns} WHERE id = ?", (*fields.values(), favorite_id))


def delete_sports_favorite(favorite_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sports_favorites WHERE id = ?", (favorite_id,))


def list_network_channel_map() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM sports_network_channel_map ORDER BY network_name").fetchall()
    return [dict(row) for row in rows]


def save_network_channel_map_entry(network_name: str, channel_id: str) -> None:
    with _connect() as conn:
        _upsert(
            conn,
            "sports_network_channel_map",
            {
                "network_name": network_name,
                "channel_id": channel_id,
                "updated_at": datetime.now(UTC).isoformat(),
            },
            key_columns=("network_name",),
        )


def delete_network_channel_map_entry(network_name: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sports_network_channel_map WHERE network_name = ?", (network_name,))


def list_tracked_events() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM sports_tracked_events ORDER BY start_ts").fetchall()
    return [dict(row) for row in rows]


def list_unresolved_tracked_events() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM sports_tracked_events WHERE recording_rule_id IS NULL ORDER BY start_ts"
        ).fetchall()
    return [dict(row) for row in rows]


def list_tracked_events_for_favorite(favorite_id: str) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM sports_tracked_events WHERE favorite_id = ?", (favorite_id,)).fetchall()
    return [dict(row) for row in rows]


def upsert_tracked_event(event: dict[str, Any]) -> None:
    with _connect() as conn:
        _upsert(
            conn,
            "sports_tracked_events",
            {
                "espn_event_id": event["espn_event_id"],
                "favorite_id": event["favorite_id"],
                "recording_rule_id": event.get("recording_rule_id"),
                "league": event["league"],
                "start_ts": event["start_ts"],
                "network_name": event.get("network_name"),
                "title_resolved": int(event.get("title_resolved", False)),
                "updated_at": event.get("updated_at") or datetime.now(UTC).isoformat(),
            },
            key_columns=("espn_event_id",),
        )


def delete_tracked_event(espn_event_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM sports_tracked_events WHERE espn_event_id = ?", (espn_event_id,))
