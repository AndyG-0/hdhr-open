"""Discovery: local category-based recommendations for upcoming guide airings.

Scores upcoming airings against a taste profile built from the household's
completed recordings' free-text `category` column (Schedules Direct genres /
XMLTV `<category>`) - the same signal `poster_lookup.classify_category` and
recording rules already key off, so no external service (e.g. TMDB) is
needed. On a fresh install with zero completed recordings there's nothing to
build a taste profile from, so `get_discovery_recommendations` falls back to
a non-personalized "new & notable" tier instead of returning nothing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.api.guide import row_to_airing
from app.config import resolve_guide_provider_priority
from app.dvr.builtin.poster_lookup import classify_category
from app.dvr.builtin.rule_expander import DEFAULT_LOOKAHEAD_SECONDS, _match_airing, normalize_title
from app.storage import db

# A completed recording from this many seconds ago counts for half as much
# as one made today, so the taste profile tracks what the household watches
# *now*, not what it watched once a year ago.
_HALF_LIFE_SECONDS = 60 * 24 * 3600  # 60 days

_MAX_RESULTS = 30

# Fallback-tier diversity caps, so a cold-start list isn't dominated by one
# genre bucket or one channel's block of premieres.
_FALLBACK_MAX_PER_BUCKET = 5
_FALLBACK_MAX_PER_CHANNEL = 3


@dataclass
class TasteProfile:
    has_data: bool
    category_weights: dict[str, float]
    bucket_weights: dict[str, float]
    recorded_titles: set[str]


def _tokenize_category(category: str | None) -> list[str]:
    if not category:
        return []
    return [normalize_title(t) for t in category.split(",") if t.strip()]


def build_taste_profile(now: float | None = None) -> TasteProfile:
    now = now if now is not None else time.time()
    recordings = db.list_completed_recordings()

    category_weights: dict[str, float] = {}
    bucket_weights: dict[str, float] = {"shows": 0.0, "movies": 0.0, "sports": 0.0}
    recorded_titles: set[str] = set()

    for r in recordings:
        age_seconds = max(0.0, now - (r.get("start_ts") or now))
        weight = 0.5 ** (age_seconds / _HALF_LIFE_SECONDS)

        for token in _tokenize_category(r.get("category")):
            category_weights[token] = category_weights.get(token, 0.0) + weight

        bucket = classify_category(
            title=r.get("title") or "", episode_title=r.get("episode_title"), category=r.get("category")
        )
        bucket_weights[bucket] = bucket_weights.get(bucket, 0.0) + weight

        title = r.get("title")
        if title:
            recorded_titles.add(normalize_title(title))

    return TasteProfile(
        has_data=bool(recordings),
        category_weights=category_weights,
        bucket_weights=bucket_weights,
        recorded_titles=recorded_titles,
    )


def _gather_candidates(now: float) -> list[dict[str, Any]]:
    """Upcoming guide airings, deduped across providers, excluding anything
    an active builtin recording rule already covers - the same lookahead
    scan `rule_expander.expand_rules_sync` runs, minus the rule-matching
    scheduling step."""
    channels = db.list_channels(True)
    channels_by_id = {c["id"]: c for c in channels}
    all_channel_ids = list(channels_by_id.keys())
    if not all_channel_ids:
        return []

    raw_programs = db.list_guide_programs(all_channel_ids, now, now + DEFAULT_LOOKAHEAD_SECONDS)
    priority = resolve_guide_provider_priority()
    resolved_by_channel = db.resolve_guide_programs(channels, raw_programs, priority)

    active_rules = db.list_recording_rules(provider="builtin")

    candidates: list[dict[str, Any]] = []
    for channel_id, programs in resolved_by_channel.items():
        channel = channels_by_id[channel_id]
        for prog in programs:
            if prog["start_ts"] <= now:
                continue
            if any(_match_airing(rule, prog) for rule in active_rules):
                continue
            candidates.append({**prog, "_channel_number": channel["channel_number"]})
    return candidates


def _score_candidate(prog: dict[str, Any], profile: TasteProfile) -> float:
    score = sum(profile.category_weights.get(token, 0.0) for token in _tokenize_category(prog.get("category")))
    if score <= 0:
        # classify_category defaults to "shows" for anything that isn't
        # clearly sports/movies, so most content would land in the same
        # bucket as most history - only use the bucket weight to rank
        # among candidates that already share a real category token,
        # never as the sole reason a candidate scores above zero.
        return 0.0
    bucket = classify_category(
        title=prog.get("title") or "", episode_title=prog.get("episode_title"), category=prog.get("category")
    )
    return score + profile.bucket_weights.get(bucket, 0.0) * 0.25


def _fallback_new_and_notable(candidates: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    fresh = sorted((c for c in candidates if c.get("is_new")), key=lambda c: c["start_ts"])

    per_bucket: dict[str, int] = {}
    per_channel: dict[str, int] = {}
    selected: list[dict[str, Any]] = []
    for prog in fresh:
        bucket = classify_category(
            title=prog.get("title") or "", episode_title=prog.get("episode_title"), category=prog.get("category")
        )
        channel_id = prog["channel_id"]
        if per_bucket.get(bucket, 0) >= _FALLBACK_MAX_PER_BUCKET:
            continue
        if per_channel.get(channel_id, 0) >= _FALLBACK_MAX_PER_CHANNEL:
            continue
        per_bucket[bucket] = per_bucket.get(bucket, 0) + 1
        per_channel[channel_id] = per_channel.get(channel_id, 0) + 1
        selected.append(prog)
        if len(selected) >= limit:
            break

    return [row_to_airing(prog, prog["_channel_number"]) for prog in selected]


def get_discovery_recommendations(limit: int = _MAX_RESULTS) -> dict[str, Any]:
    now = time.time()
    profile = build_taste_profile(now)
    candidates = _gather_candidates(now)

    if profile.has_data:
        scored: list[tuple[float, dict[str, Any]]] = []
        for prog in candidates:
            if normalize_title(prog.get("title") or "") in profile.recorded_titles:
                continue
            score = _score_candidate(prog, profile)
            if score > 0:
                scored.append((score, prog))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        items = [row_to_airing(prog, prog["_channel_number"]) for _, prog in scored[:limit]]
        return {"has_profile": True, "items": items}

    return {"has_profile": False, "items": _fallback_new_and_notable(candidates, limit)}
