"""Channels and guide data: lineup, per-provider airings, and the
XMLTV/Schedules Direct channel/program mapping caches.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from app.storage.db.connection import _connect, _upsert, _validate_update_columns

_CHANNEL_UPDATABLE_COLUMNS = frozenset(
    {"name", "is_hd", "is_favorite", "hidden", "sort_order", "guide_provider"}
)


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
    _validate_update_columns("channels", _CHANNEL_UPDATABLE_COLUMNS, fields)
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


def _normalize_guide_title(t: str | None) -> str:
    if not t:
        return ""
    import re

    return re.sub(r"[^\w\s]", "", t).strip().lower()


def resolve_guide_programs(
    channels: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    default_priority: tuple[str, ...] = DEFAULT_GUIDE_PROVIDER_PRIORITY,
) -> dict[str, list[dict[str, Any]]]:
    """Collapse list_guide_programs()'s unfiltered, possibly multi-provider
    rows down to one effective list of guide airings per channel.
    Higher-priority provider airings take precedence, and any gaps (such as
    missing current or earlier airings) are filled in from lower-priority
    providers. Additionally enriches airings lacking an external_program_id (e.g.
    XMLTV feeds) from co-occurring airings on other providers with matching time and title."""
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
            # Build an index of other provider airings on this channel that have external_program_id
            enrichment_candidates: list[dict[str, Any]] = []
            for p, p_rows in by_provider.items():
                for pr in p_rows:
                    if pr.get("external_program_id"):
                        enrichment_candidates.append(pr)

            resolved_rows: list[dict[str, Any]] = []
            for row in merged_rows:
                r = dict(row)
                if not r.get("external_program_id") and enrichment_candidates:
                    r_start = r.get("start_ts")
                    norm_r_title = _normalize_guide_title(r.get("title"))
                    if r_start is not None:
                        for c in enrichment_candidates:
                            c_start = c.get("start_ts")
                            if c_start is not None and abs(c_start - r_start) <= 60:
                                norm_c_title = _normalize_guide_title(c.get("title"))
                                if norm_r_title and norm_c_title and (
                                    norm_r_title == norm_c_title
                                    or norm_r_title in norm_c_title
                                    or norm_c_title in norm_r_title
                                ):
                                    r["external_program_id"] = c["external_program_id"]
                                    if not r.get("image_url") and c.get("image_url"):
                                        r["image_url"] = c["image_url"]
                                    if not r.get("synopsis") and c.get("synopsis"):
                                        r["synopsis"] = c["synopsis"]
                                    if not r.get("episode_title") and c.get("episode_title"):
                                        r["episode_title"] = c["episode_title"]
                                    if r.get("season_number") is None and c.get("season_number") is not None:
                                        r["season_number"] = c["season_number"]
                                    if r.get("episode_number") is None and c.get("episode_number") is not None:
                                        r["episode_number"] = c["episode_number"]
                                    break
                resolved_rows.append(r)

            result[channel["id"]] = sorted(resolved_rows, key=lambda r: r["start_ts"])
    return result
