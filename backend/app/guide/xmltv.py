"""XMLTV guide persistence.

Runs as a scheduled background job (see register()), pulling a user-supplied
XMLTV feed URL (the `xmltv` network integration's `settings["url"]`) and
writing it into guide_programs / xmltv_channel_map so app.api.guide can read
purely from the DB, same pattern as app.guide.service's "hdhomerun_cloud"
provider. This module only owns the "xmltv" provider.

Channel mapping is exact-match auto-mapping only: on each refresh, any tuner
channel with no existing xmltv_channel_map row is matched against the feed's
<channel id>/<display-name> values by exact equality to that channel's
channel_number. A manually-seeded map row is never overwritten.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import effective_settings, resolve_timezone
from app.storage import db

logger = logging.getLogger(__name__)

SOURCE_PROVIDER = "xmltv"
REFRESH_INTERVAL_SECONDS = 3600
_JOB_ID = "guide_refresh_xmltv"
_ONSCREEN_EPISODE_RE = re.compile(r"^\s*(?:[Ss](\d+))?\s*[Ee](\d+)\s*$")
_ONSCREEN_SEASON_DOT_EPISODE_RE = re.compile(r"^\s*(\d+)\s*\.\s*(\d+)\s*$")


def register(scheduler: AsyncIOScheduler) -> None:
    scheduler.add_job(
        refresh_xmltv_guide,
        "interval",
        seconds=REFRESH_INTERVAL_SECONDS,
        id=_JOB_ID,
        replace_existing=True,  # safe to re-register across app restarts / test sessions
        next_run_time=datetime.now(UTC),  # bootstrap: fetch once immediately, then on the interval
        max_instances=1,
        coalesce=True,
    )


async def _xmltv_settings_or_none() -> dict[str, Any] | None:
    row = await asyncio.to_thread(db.get_network_integration, "xmltv")
    return row["settings"] if row else None


def _parse_xmltv_time(value: str | None, default_tz: ZoneInfo | None = None) -> float | None:
    """Parse XMLTV timestamps supporting 14/12/8 digit timestamps with/without
    timezone offsets (e.g. "+0000", "+00:00", "-0700", "-07:00", "Z", "UTC"),
    and ISO 8601 strings. Unspecified offsets fall back to default_tz (or UTC)."""
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None

    # Handle ISO 8601 format (e.g. 2026-08-23T19:00:00Z or 2026-08-23 19:00:00+00:00)
    if "-" in raw[:10]:
        try:
            clean = raw.replace("Z", "+00:00")
            dt = datetime.fromisoformat(clean)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=default_tz or UTC)
            return dt.timestamp()
        except (ValueError, TypeError):
            pass

    # Standard XMLTV format: YYYYMMDD[HH[MM[SS]]] [+/-HHMM or +/-HH:MM or Z or UTC]
    match = re.match(r"^(\d{8,14})(?:\s*([+-]\d{2}:?\d{2}|Z|UTC|GMT))?", raw)
    if not match:
        return None

    digits, tz_part = match.groups()
    if len(digits) == 8:
        digits += "000000"
    elif len(digits) == 10:
        digits += "0000"
    elif len(digits) == 12:
        digits += "00"
    elif len(digits) > 14:
        digits = digits[:14]

    try:
        dt = datetime.strptime(digits, "%Y%m%d%H%M%S")
    except ValueError:
        return None

    if tz_part:
        if tz_part in ("Z", "UTC", "GMT"):
            tz = UTC
        else:
            tz_clean = tz_part.replace(":", "")
            sign = 1 if tz_clean[0] == "+" else -1
            hours = int(tz_clean[1:3])
            minutes = int(tz_clean[3:5])
            tz = timezone(sign * timedelta(hours=hours, minutes=minutes))
    else:
        tz = default_tz or UTC

    return dt.replace(tzinfo=tz).timestamp()


async def _fetch_xmltv_root(url: str) -> ElementTree.Element | None:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
        if response.status_code >= 400:
            return None
        return ElementTree.fromstring(response.content)
    except (httpx.HTTPError, ElementTree.ParseError):
        logger.debug("Could not fetch/parse XMLTV guide from '%s'", url, exc_info=True)
        return None


def _parse_channels(root: ElementTree.Element) -> dict[str, list[str]]:
    channels: dict[str, list[str]] = {}
    for channel_el in root.findall("channel"):
        channel_id = channel_el.get("id")
        if not channel_id:
            continue
        names = [el.text.strip() for el in channel_el.findall("display-name") if el.text and el.text.strip()]
        channels[channel_id] = names
    return channels


def _parse_episode_num(programme_el: ElementTree.Element) -> tuple[int | None, int | None]:
    onscreen: str | None = None
    for el in programme_el.findall("episode-num"):
        system = el.get("system")
        text = (el.text or "").strip()
        if not text:
            continue
        if system == "xmltv_ns":
            parts = text.split(".")
            if len(parts) >= 2:
                season_raw, episode_raw = parts[0].strip(), parts[1].strip()
                season = int(season_raw) + 1 if season_raw else None
                episode = int(episode_raw) + 1 if episode_raw else None
                if season is not None or episode is not None:
                    return season, episode
        elif system == "onscreen":
            onscreen = text
    if onscreen:
        match = _ONSCREEN_EPISODE_RE.match(onscreen)
        if match:
            season_raw, episode_raw = match.groups()
            return (int(season_raw) if season_raw else None), int(episode_raw)
        match = _ONSCREEN_SEASON_DOT_EPISODE_RE.match(onscreen)
        if match:
            return int(match.group(1)), int(match.group(2))
    return None, None


def _parse_categories(programme_el: ElementTree.Element) -> str | None:
    categories = [el.text.strip() for el in programme_el.findall("category") if el.text and el.text.strip()]
    return ", ".join(categories) if categories else None


def _parse_icon(programme_el: ElementTree.Element) -> str | None:
    icon_el = programme_el.find("icon")
    return icon_el.get("src") if icon_el is not None else None


def _parse_desc(programme_el: ElementTree.Element) -> str | None:
    desc_el = programme_el.find("desc")
    return desc_el.text.strip() if desc_el is not None and desc_el.text else None


def _parse_date(programme_el: ElementTree.Element) -> str | None:
    date_el = programme_el.find("date")
    return date_el.text.strip() if date_el is not None and date_el.text else None


def _parse_is_new(programme_el: ElementTree.Element) -> bool:
    return programme_el.find("new") is not None


def _programme_to_row(
    channel_id: str, programme_el: ElementTree.Element, default_tz: ZoneInfo | None = None
) -> dict[str, Any] | None:
    start = _parse_xmltv_time(programme_el.get("start"), default_tz)
    if start is None:
        return None
    end = _parse_xmltv_time(programme_el.get("stop"), default_tz)
    if end is None:
        length_el = programme_el.find("length")
        if length_el is not None and length_el.text and length_el.text.strip():
            try:
                length_val = float(length_el.text.strip())
                units = (length_el.get("units") or "minutes").lower()
                if "hour" in units:
                    end = start + length_val * 3600
                elif "sec" in units:
                    end = start + length_val
                else:
                    end = start + length_val * 60
            except ValueError:
                end = start + 1800
        else:
            end = start + 1800

    title_el = programme_el.find("title")
    subtitle_el = programme_el.find("sub-title")
    season_number, episode_number = _parse_episode_num(programme_el)
    return {
        "channel_id": channel_id,
        "source_provider": SOURCE_PROVIDER,
        "external_program_id": None,
        "title": (title_el.text or "").strip() if title_el is not None and title_el.text else "",
        "episode_title": subtitle_el.text.strip() if subtitle_el is not None and subtitle_el.text else None,
        "season_number": season_number,
        "episode_number": episode_number,
        "synopsis": _parse_desc(programme_el),
        "start_ts": start,
        "end_ts": end,
        "original_air_date": _parse_date(programme_el),
        "image_url": _parse_icon(programme_el),
        "is_new": int(_parse_is_new(programme_el)),
        "category": _parse_categories(programme_el),
    }


def _auto_map_unmapped_channels(xmltv_channels: dict[str, list[str]]) -> None:
    tuner_channels = db.list_channels(True)
    already_mapped = {row["channel_id"] for row in db.list_xmltv_channel_map()}
    for channel in tuner_channels:
        if channel["id"] in already_mapped:
            continue
        number = channel["channel_number"].strip()
        name = (channel.get("name") or "").strip().lower()
        num_dot = number.lower()
        num_clean = number.replace(".", "").lower()
        num_hyphen = number.replace(".", "-").lower()
        num_under = number.replace(".", "_").lower()

        matched_id: str | None = None
        matched_display: str | None = None

        for xmltv_channel_id, display_names in xmltv_channels.items():
            x_id_clean = xmltv_channel_id.strip()
            x_id_lower = x_id_clean.lower()
            names_lower = [d.strip().lower() for d in display_names if d and d.strip()]

            # 1. Exact match on channel number or xmltv id variations
            if (
                number == x_id_clean
                or num_dot in names_lower
                or num_hyphen in names_lower
                or x_id_lower in (num_dot, num_hyphen, num_under, num_clean)
            ):
                matched_id = x_id_clean
                matched_display = display_names[0] if display_names else None
                break

            # 2. Display name prefix / suffix / containment with channel number (e.g. "10.2 MeTV", "10-2 MeTV", "MeTV 10.2", "FOX 12.1", "12.1 KDFW")
            prefix_match = False
            for d in display_names:
                d_stripped = d.strip()
                d_lower = d_stripped.lower()
                if (
                    d_lower.startswith(f"{num_dot} ")
                    or d_lower.startswith(f"{num_dot}-")
                    or d_lower.startswith(f"{num_dot}:")
                    or d_lower.startswith(f"{num_dot}.")
                    or d_lower.startswith(f"{num_hyphen} ")
                    or d_lower.startswith(f"{num_hyphen}-")
                    or d_lower.endswith(f" {num_dot}")
                    or d_lower.endswith(f" {num_hyphen}")
                    or f"({num_dot})" in d_lower
                    or f"[{num_dot}]" in d_lower
                ):
                    matched_id = x_id_clean
                    matched_display = d_stripped
                    prefix_match = True
                    break
            if prefix_match:
                break

            # 3. Channel callsign/name matching
            if name and (name == x_id_lower or name in names_lower or any(name in n for n in names_lower)):
                matched_id = x_id_clean
                matched_display = display_names[0] if display_names else None
                break

            # 4. XMLTV ID prefix/dot matching (e.g. "I10.2", "10.2.zap2it.com", "channel-10.2")
            if (
                x_id_lower == f"i{num_dot}"
                or x_id_lower == f"c{num_dot}"
                or x_id_lower.startswith(f"{num_dot}.")
                or x_id_lower.startswith(f"{num_hyphen}.")
                or x_id_lower == num_clean
            ):
                matched_id = x_id_clean
                matched_display = display_names[0] if display_names else None
                break

        if matched_id:
            db.upsert_xmltv_channel_map(channel["id"], matched_id, matched_display)
            already_mapped.add(channel["id"])


class XMLTVError(Exception):
    """Raised when XMLTV guide reload fails."""


async def reload_xmltv_guide() -> dict[str, Any]:
    """Pull the user-configured XMLTV feed, persist it, and return fresh stats.
    Raises XMLTVError if unconfigured or fetch/parse fails."""
    settings = await _xmltv_settings_or_none()
    url = settings.get("url") if settings else None
    if not url or not url.strip():
        raise XMLTVError("XMLTV URL is not configured")

    root = await _fetch_xmltv_root(url.strip())
    if root is None:
        raise XMLTVError(f"Could not fetch or parse XMLTV feed from '{url}'")

    xmltv_channels = _parse_channels(root)
    # Also collect any channel IDs from <programme> tags that lacked <channel> headers
    for programme_el in root.findall("programme"):
        ch_attr = programme_el.get("channel")
        if ch_attr and ch_attr not in xmltv_channels:
            xmltv_channels[ch_attr] = [ch_attr]

    await asyncio.to_thread(_auto_map_unmapped_channels, xmltv_channels)

    channel_id_by_xmltv_id = {
        row["xmltv_channel_id"]: row["channel_id"] for row in await asyncio.to_thread(db.list_xmltv_channel_map)
    }

    app_settings = await asyncio.to_thread(effective_settings)
    default_tz = resolve_timezone(app_settings.get("timezone", "UTC"))

    rows_by_channel: dict[str, list[dict[str, Any]]] = {}
    skipped = 0
    for programme_el in root.findall("programme"):
        xmltv_channel_id = programme_el.get("channel")
        channel_id = channel_id_by_xmltv_id.get(xmltv_channel_id) if xmltv_channel_id else None
        if channel_id is None:
            skipped += 1
            continue
        row = _programme_to_row(channel_id, programme_el, default_tz)
        if row is not None:
            rows_by_channel.setdefault(channel_id, []).append(row)

    def _write() -> None:
        db.delete_guide_programs_by_provider(SOURCE_PROVIDER)
        for channel_id, rows in rows_by_channel.items():
            db.upsert_guide_programs(rows)

    await asyncio.to_thread(_write)
    cursor_payload = json.dumps({"channels_in_feed": len(xmltv_channels)})
    await asyncio.to_thread(
        db.save_guide_provider_state, SOURCE_PROVIDER, datetime.now(UTC).isoformat(), cursor_payload
    )
    logger.info(
        "Refreshed XMLTV guide (%d channels in feed, %d channels mapped, %d programmes written, %d skipped for no mapping)",
        len(xmltv_channels),
        len(channel_id_by_xmltv_id),
        sum(len(rows) for rows in rows_by_channel.values()),
        skipped,
    )
    return await asyncio.to_thread(db.get_xmltv_guide_stats)


async def refresh_xmltv_guide() -> None:
    """Scheduler job: pull a user-configured XMLTV feed and persist it."""
    try:
        await reload_xmltv_guide()
    except XMLTVError as exc:
        logger.info("XMLTV guide refresh skipped or failed: %s", exc)
