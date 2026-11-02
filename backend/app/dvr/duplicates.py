"""Find duplicate recordings: finished copies of the same program.

Works on the formatted recording dicts returned by GET /api/dvr/recordings,
so builtin and official HDHomeRun DVR recordings are compared the same way.
"""

from __future__ import annotations

import re
from typing import Any

from app.dvr.builtin.poster_lookup import classify_category

_WHITESPACE = re.compile(r"\s+")
_SXXEYY = re.compile(r"^s(\d+)\s*e(\d+)$", re.IGNORECASE)
_DOTTED = re.compile(r"^(\d+)\.(\d+)$")


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return _WHITESPACE.sub(" ", str(value)).strip().casefold()


def _episode_key(rec: dict[str, Any]) -> tuple[str, str]:
    """(season, episode) as normalized strings.

    Builtin recordings send episode_number as "S.E" (plus season_number);
    official HDHomeRun recordings send "S01E02". Both reduce to ("1", "2").
    """
    season = _norm(rec.get("season_number"))
    episode = _norm(rec.get("episode_number"))
    match = _SXXEYY.match(episode) or _DOTTED.match(episode)
    if match:
        return str(int(match.group(1))), str(int(match.group(2)))
    if season.isdigit():
        season = str(int(season))
    if episode.isdigit():
        episode = str(int(episode))
    return season, episode


def _category_type(rec: dict[str, Any]) -> str:
    return rec.get("category_type") or classify_category(
        title=rec.get("title") or "",
        episode_title=rec.get("episode_title"),
        category=rec.get("category"),
    )


def _is_finished(rec: dict[str, Any], now: float) -> bool:
    status = rec.get("status")
    if status and status != "completed":
        return False
    record_end = rec.get("record_end")
    return record_end is not None and record_end <= now


def duplicate_key(rec: dict[str, Any], now: float) -> tuple[str, ...] | None:
    """The key that identifies `rec`'s program, or None if it can't be grouped."""
    if not rec.get("recording_id") or not _is_finished(rec, now):
        return None
    title = _norm(rec.get("title"))
    if not title:
        return None
    category_type = _category_type(rec)
    episode_title = _norm(rec.get("episode_title"))
    season, episode = _episode_key(rec)
    air_date = _norm(rec.get("original_air_date"))
    # A show or game with no details at all (e.g. a daily newscast) can't be
    # told apart from its other airings, so don't call those duplicates.
    if category_type != "movies" and not (episode_title or season or episode or air_date):
        return None
    return (category_type, title, episode_title, season, episode, air_date)


def _keeper_rank(rec: dict[str, Any]) -> tuple[float, float, float, float]:
    return (
        rec.get("file_size_bytes") or 0,
        rec.get("duration_seconds") or 0,
        rec.get("video_height") or 0,
        rec.get("start") or 0,
    )


def find_duplicate_groups(recordings: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    """Groups of 2+ finished recordings of the same program.

    Each group names a suggested keeper: the largest file, then the longest,
    then the highest resolution, then the newest.
    """
    buckets: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    seen_ids: set[str] = set()
    for rec in recordings:
        key = duplicate_key(rec, now)
        if key is None or rec["recording_id"] in seen_ids:
            continue
        seen_ids.add(rec["recording_id"])
        buckets.setdefault(key, []).append(rec)

    groups = []
    for key, recs in buckets.items():
        if len(recs) < 2:
            continue
        recs.sort(key=lambda r: r.get("start") or 0, reverse=True)
        keeper = max(recs, key=_keeper_rank)
        groups.append(
            {
                "key": "|".join(key),
                "title": keeper.get("title") or "",
                "episode_title": keeper.get("episode_title"),
                "category_type": key[0],
                "suggested_keep_id": keeper["recording_id"],
                "recordings": recs,
            }
        )
    groups.sort(key=lambda g: (_norm(g["title"]), g["key"]))
    return groups
