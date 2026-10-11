"""Discovery: local, per-bucket (shows/movies/sports) recommendations for
upcoming guide airings.

For each bucket, candidates are pulled from an ordered cascade of signals
until that bucket's share of the result is filled or every signal runs dry:

1. `personalized` - the household's own completed-recordings history
   (`build_taste_profile`), scored against free-text `category` overlap -
   the same signal `poster_lookup.classify_category` and recording rules
   already key off, so no external service (e.g. TMDB) is needed.
2. `active_rule` - categories/titles the household has an *active* builtin
   recording rule for, even if nothing has completed recording yet
   (`build_rule_intent_profile`). A household that just set up a rule for a
   genre clearly cares about it before anything airs.
3. `favorite_team` (sports only) - upcoming games for the household's
   favorited sports teams, read from the cache `sports_autorecord`'s
   background sync already maintains (`sports_tracked_events`) rather than
   calling ESPN directly from this request path.
4. `network_pick` - new/first-run airings on a channel whose broadcast
   affiliate (NBC/CBS/ABC/FOX/CW) is known, for households with no signal
   above yet.
5. `new_and_notable` - new/first-run airings, no personalization at all.
   The last resort, so a bucket never comes back empty.

Every returned item is tagged with the `bucket` it was classified into and
the `source` tier that produced it, so clients can filter locally and show
"why this is here" without a second round-trip.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.api.guide import row_to_airing
from app.config import resolve_guide_provider_priority
from app.dvr.builtin.network_affiliates import is_major_network
from app.dvr.builtin.poster_lookup import classify_category
from app.dvr.builtin.rule_expander import DEFAULT_LOOKAHEAD_SECONDS, _match_airing, normalize_title
from app.storage import db

# A completed recording from this many seconds ago counts for half as much
# as one made today, so the taste profile tracks what the household watches
# *now*, not what it watched once a year ago.
_HALF_LIFE_SECONDS = 60 * 24 * 3600  # 60 days

_MAX_RESULTS = 200
_BUCKETS = ("shows", "movies", "sports")

# A favorite team's cached upcoming game (`sports_tracked_events`) is
# matched to a guide candidate by channel + approximate start time, since
# the tracked-event row doesn't carry a guide_program_id of its own.
_FAVORITE_TEAM_MATCH_WINDOW_SECONDS = 30 * 60

# So one channel's block of premieres can't dominate the non-personalized
# tiers (3/4/5 all draw from "new/first-run" airings).
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


def _bucket_of(prog: dict[str, Any]) -> str:
    return classify_category(
        title=prog.get("title") or "", episode_title=prog.get("episode_title"), category=prog.get("category")
    )


def build_taste_profile(now: float | None = None) -> TasteProfile:
    now = now if now is not None else time.time()
    recordings = db.list_completed_recordings()

    category_weights: dict[str, float] = {}
    bucket_weights: dict[str, float] = {b: 0.0 for b in _BUCKETS}
    recorded_titles: set[str] = set()

    for r in recordings:
        age_seconds = max(0.0, now - (r.get("start_ts") or now))
        weight = 0.5 ** (age_seconds / _HALF_LIFE_SECONDS)

        for token in _tokenize_category(r.get("category")):
            category_weights[token] = category_weights.get(token, 0.0) + weight

        bucket_weights[_bucket_of(r)] = bucket_weights.get(_bucket_of(r), 0.0) + weight

        title = r.get("title")
        if title:
            recorded_titles.add(normalize_title(title))

    return TasteProfile(
        has_data=bool(recordings),
        category_weights=category_weights,
        bucket_weights=bucket_weights,
        recorded_titles=recorded_titles,
    )


def build_rule_intent_profile(now: float | None = None) -> TasteProfile:
    """A lighter-weight TasteProfile built from the household's *active*
    builtin recording rules rather than completed recordings - lets a bucket
    keep recommending things the household has clearly set out to record,
    even before anything has actually finished recording yet.

    `recording_rules` itself has no category column, so category signal
    only exists once a rule has expanded into at least one upcoming
    `scheduled_recordings` instance (those rows carry `category` from the
    matched guide program). A rule with no expansion yet still contributes
    a bucket signal classified from its title alone, at a lower weight,
    since there's no guide-derived category text to tokenize for it.
    """
    now = now if now is not None else time.time()
    scheduled = db.list_scheduled_recordings(status="scheduled")
    instances_by_rule: dict[str, list[dict[str, Any]]] = {}
    for s in scheduled:
        rule_id = s.get("rule_id")
        if rule_id:
            instances_by_rule.setdefault(rule_id, []).append(s)

    category_weights: dict[str, float] = {}
    bucket_weights: dict[str, float] = {b: 0.0 for b in _BUCKETS}
    has_data = False

    for rule in db.list_recording_rules(provider="builtin"):
        instances = instances_by_rule.get(rule["id"], [])
        if instances:
            has_data = True
            tokens: set[str] = set()
            for inst in instances:
                tokens.update(_tokenize_category(inst.get("category")))
            for token in tokens:
                category_weights[token] = category_weights.get(token, 0.0) + 1.0
            bucket_weights[_bucket_of(instances[0])] += 1.0
        else:
            has_data = True
            bucket = classify_category(title=rule.get("title") or "", episode_title=None, category=None)
            bucket_weights[bucket] += 0.5

    return TasteProfile(
        has_data=has_data, category_weights=category_weights, bucket_weights=bucket_weights, recorded_titles=set()
    )


def _gather_candidates(now: float) -> list[dict[str, Any]]:
    """Upcoming guide airings, deduped across providers, excluding anything
    an active builtin recording rule already covers - the same lookahead
    scan `rule_expander.expand_rules_sync` runs, minus the rule-matching
    scheduling step. The exact airing a rule covers should never be
    "discovered" again; `build_rule_intent_profile` only reuses the rule's
    *category signal*, applied to whatever candidates remain."""
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
            candidates.append(
                {**prog, "_channel_number": channel["channel_number"], "_affiliate": channel.get("affiliate")}
            )
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
    return score + profile.bucket_weights.get(_bucket_of(prog), 0.0) * 0.25


def _candidate_key(prog: dict[str, Any]) -> tuple[Any, Any]:
    return (prog.get("channel_id"), prog.get("start_ts"))


def _take_scored(
    candidates: list[dict[str, Any]],
    profile: TasteProfile,
    source: str,
    bucket: str,
    chosen_keys: set[tuple[Any, Any]],
    picks: list[tuple[str, str, float, dict[str, Any]]],
    limit: int,
) -> int:
    if limit <= 0:
        return 0
    scored: list[tuple[float, dict[str, Any]]] = []
    for prog in candidates:
        if _candidate_key(prog) in chosen_keys:
            continue
        score = _score_candidate(prog, profile)
        if score > 0:
            scored.append((score, prog))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    taken = 0
    for score, prog in scored[:limit]:
        chosen_keys.add(_candidate_key(prog))
        picks.append((bucket, source, score, prog))
        taken += 1
    return taken


def _take_favorite_team(
    candidates: list[dict[str, Any]],
    chosen_keys: set[tuple[Any, Any]],
    picks: list[tuple[str, str, float, dict[str, Any]]],
    limit: int,
) -> int:
    if limit <= 0:
        return 0
    tracked = db.list_tracked_events()
    if not tracked:
        return 0
    network_map = {row["network_name"]: row["channel_id"] for row in db.list_network_channel_map()}

    by_channel: dict[str, list[dict[str, Any]]] = {}
    for prog in candidates:
        channel_id = prog.get("channel_id")
        if channel_id is None:
            continue
        by_channel.setdefault(channel_id, []).append(prog)

    taken = 0
    for event in sorted(tracked, key=lambda e: e["start_ts"]):
        if taken >= limit:
            break
        channel_id = network_map.get(event.get("network_name"))
        if channel_id is None:
            continue
        for prog in by_channel.get(channel_id, []):
            key = _candidate_key(prog)
            if key in chosen_keys:
                continue
            if abs(prog["start_ts"] - event["start_ts"]) <= _FAVORITE_TEAM_MATCH_WINDOW_SECONDS:
                chosen_keys.add(key)
                picks.append(("sports", "favorite_team", 0.0, prog))
                taken += 1
                break
    return taken


def _take_network_pick(
    candidates: list[dict[str, Any]],
    bucket: str,
    chosen_keys: set[tuple[Any, Any]],
    picks: list[tuple[str, str, float, dict[str, Any]]],
    per_channel: dict[str, int],
    limit: int,
) -> int:
    if limit <= 0:
        return 0
    fresh = sorted(
        (c for c in candidates if c.get("is_new") and is_major_network(c.get("_affiliate"))),
        key=lambda c: c["start_ts"],
    )
    return _take_fresh(fresh, bucket, "network_pick", chosen_keys, picks, per_channel, limit)


def _take_new_and_notable(
    candidates: list[dict[str, Any]],
    bucket: str,
    chosen_keys: set[tuple[Any, Any]],
    picks: list[tuple[str, str, float, dict[str, Any]]],
    per_channel: dict[str, int],
    limit: int,
) -> int:
    if limit <= 0:
        return 0
    fresh = sorted((c for c in candidates if c.get("is_new")), key=lambda c: c["start_ts"])
    return _take_fresh(fresh, bucket, "new_and_notable", chosen_keys, picks, per_channel, limit)


def _take_fresh(
    fresh: list[dict[str, Any]],
    bucket: str,
    source: str,
    chosen_keys: set[tuple[Any, Any]],
    picks: list[tuple[str, str, float, dict[str, Any]]],
    per_channel: dict[str, int],
    limit: int,
) -> int:
    taken = 0
    for prog in fresh:
        if taken >= limit:
            break
        key = _candidate_key(prog)
        if key in chosen_keys:
            continue
        channel_id = prog.get("channel_id")
        if channel_id is None:
            continue
        if per_channel.get(channel_id, 0) >= _FALLBACK_MAX_PER_CHANNEL:
            continue
        chosen_keys.add(key)
        per_channel[channel_id] = per_channel.get(channel_id, 0) + 1
        picks.append((bucket, source, 0.0, prog))
        taken += 1
    return taken


def _to_discovery_item(prog: dict[str, Any], bucket: str, source: str) -> dict[str, Any]:
    item = row_to_airing(prog, prog["_channel_number"])
    item["bucket"] = bucket
    item["source"] = source
    return item


def get_discovery_recommendations(limit: int = _MAX_RESULTS) -> dict[str, Any]:
    now = time.time()
    profile = build_taste_profile(now)
    rule_profile = build_rule_intent_profile(now)
    candidates = _gather_candidates(now)

    by_bucket: dict[str, list[dict[str, Any]]] = {b: [] for b in _BUCKETS}
    for prog in candidates:
        if normalize_title(prog.get("title") or "") in profile.recorded_titles:
            continue
        by_bucket[_bucket_of(prog)].append(prog)

    chosen_keys: set[tuple[Any, Any]] = set()
    picks: list[tuple[str, str, float, dict[str, Any]]] = []
    per_channel: dict[str, int] = {}

    def _fill_bucket(bucket: str, cap: int) -> int:
        remaining = cap
        remaining -= _take_scored(by_bucket[bucket], profile, "personalized", bucket, chosen_keys, picks, remaining)
        if remaining > 0:
            remaining -= _take_scored(
                by_bucket[bucket], rule_profile, "active_rule", bucket, chosen_keys, picks, remaining
            )
        if bucket == "sports" and remaining > 0:
            remaining -= _take_favorite_team(by_bucket[bucket], chosen_keys, picks, remaining)
        if remaining > 0:
            remaining -= _take_network_pick(by_bucket[bucket], bucket, chosen_keys, picks, per_channel, remaining)
        if remaining > 0:
            remaining -= _take_new_and_notable(by_bucket[bucket], bucket, chosen_keys, picks, per_channel, remaining)
        return cap - remaining

    # Every bucket gets an equal base share of `limit` first; any share a
    # bucket can't use (it ran out of candidates across all five tiers)
    # gets redistributed, a round at a time, to buckets that are still
    # producing picks - until `limit` is reached or no bucket has anything
    # left to give.
    active_buckets = list(_BUCKETS)
    round_cap = max(1, limit // len(_BUCKETS))
    while active_buckets and len(picks) < limit:
        still_active: list[str] = []
        for bucket in active_buckets:
            taken = _fill_bucket(bucket, round_cap)
            if taken > 0:
                still_active.append(bucket)
            if len(picks) >= limit:
                break
        active_buckets = still_active
        leftover = limit - len(picks)
        if leftover <= 0 or not active_buckets:
            break
        round_cap = max(1, leftover // len(active_buckets))

    picks.sort(key=lambda p: (-p[2], p[3]["start_ts"]))
    items = [_to_discovery_item(prog, bucket, source) for bucket, source, _, prog in picks[:limit]]
    return {"has_profile": profile.has_data, "items": items}
