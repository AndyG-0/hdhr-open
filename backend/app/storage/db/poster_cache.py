"""Persistent cache of resolved TMDb/TheSportsDB poster lookups, shared by
guide ingestion, discovery, and recording-completion poster backfill (see
app.dvr.builtin.poster_lookup) so the same program is never looked up twice.
"""

from __future__ import annotations

from typing import Any

from app.storage.db.connection import _connect, _upsert


def get_cached_posters(cache_keys: list[str]) -> dict[str, dict[str, Any]]:
    """Batch-fetch; returned keys have been looked up before (hit or
    confirmed miss). A key absent from the result has never been looked up."""
    if not cache_keys:
        return {}
    result: dict[str, dict[str, Any]] = {}
    with _connect() as conn:
        placeholders = ",".join("?" for _ in cache_keys)
        rows = conn.execute(
            f"SELECT cache_key, category, poster_url, looked_up_at FROM poster_url_cache "
            f"WHERE cache_key IN ({placeholders})",
            cache_keys,
        ).fetchall()
        for r in rows:
            result[r["cache_key"]] = dict(r)
    return result


def upsert_poster_cache(entries: list[dict[str, Any]]) -> None:
    """Each entry: {cache_key, category, poster_url (nullable), looked_up_at}."""
    if not entries:
        return
    with _connect() as conn:
        for entry in entries:
            _upsert(conn, "poster_url_cache", entry, ("cache_key",))


def delete_expired_poster_cache(before_iso: str) -> None:
    """Only purges confirmed misses (poster_url IS NULL) - a confirmed hit
    is never expired, since posters don't change once found."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM poster_url_cache WHERE poster_url IS NULL AND looked_up_at < ?",
            (before_iso,),
        )
