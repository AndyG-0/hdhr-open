"""Ad hoc "watch" sessions: an auto-started, hidden recording behind every live
channel open, so the existing in-progress-recording playback path (pause,
rewind, scrub — see app/api/dvr.py's recording-stream/recording-detail) works
for live TV too. Orchestrates app.dvr.builtin.capture/tuner_allocator the same
way app.dvr.builtin.engine does for scheduled recordings, just triggered by a
viewer opening a channel instead of the engine's tick.

Every call to start_watch mints a fresh session_id identifying *this viewer's*
lifecycle. If a capture is already running on the requested channel (another
viewer, or a scheduled recording), the new session just attaches to it —
no second tuner, no second ffmpeg — and shares the same recording_id as
everyone else watching that channel. The capture itself is only ever torn
down when it's still temporary (never promoted to a real recording) and its
last attached viewer session leaves.

Lifecycle: start_watch on channel open -> heartbeat_watch every ~20s while the
player is open -> either stop_watch (player closed) or promote_watch (user hit
Record, so the capture becomes a real recording independent of any viewer).
reap_stale_watches is the crash/lost-connection backstop for sessions that
never got an explicit stop.

The session registry is in-memory only (not DB-persisted), consistent with
the rest of the engine's crash-recovery model: on a process restart there are
no viewers left to reconnect to old sessions anyway, and
DVREngine.recover_on_startup already discards any dangling temporary
recording found in the database.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from app.dvr.builtin.capture import ActiveCapture, capture_pipeline
from app.dvr.builtin.retention import delete_local_recording
from app.dvr.builtin.tuner_allocator import tuner_allocator
from app.storage import db

logger = logging.getLogger(__name__)

# Safety cap on a single auto-capture's length, independent of the heartbeat
# reaper below - belt and suspenders against a runaway ffmpeg process if the
# reaper somehow never runs.
WATCH_MAX_DURATION_SECONDS = 4 * 3600

# A live-watch session that hasn't heartbeat-ed in this long is assumed
# abandoned (crashed tab, lost network, force-closed browser) and reaped by
# DVREngine.tick(). Comfortably more than one missed heartbeat interval
# (frontend pings roughly every 20s).
WATCH_HEARTBEAT_TIMEOUT_SECONDS = 60


@dataclass
class _WatchSession:
    session_id: str
    recording_id: str
    channel_number: str
    last_heartbeat_at: float


_sessions: dict[str, _WatchSession] = {}


async def start_watch(channel_number: str, settings: dict[str, Any]) -> dict[str, str] | None:
    """Start (or attach to) a live-watch session for channel_number. Returns
    {"recording_id", "session_id"}, or None if no tuner is available and no
    capture already exists for this channel - callers should fall back to
    plain live streaming (no pause/rewind) in that case."""
    session_id = uuid.uuid4().hex
    now = time.time()

    existing = await capture_pipeline.get_active_capture_by_channel(channel_number)
    if existing is not None:
        if not await tuner_allocator.acquire_tuner(session_id, channel_number, settings):
            return None
        await capture_pipeline.add_viewer(existing.recording_id, session_id)
        _sessions[session_id] = _WatchSession(session_id, existing.recording_id, channel_number, now)
        return {"recording_id": existing.recording_id, "session_id": session_id}

    if not await tuner_allocator.acquire_tuner(session_id, channel_number, settings):
        return None

    channel = await asyncio.to_thread(db.get_channel_by_number, channel_number)
    channel_name = channel["name"] if channel else channel_number

    # Look up current airing on this channel to seed rich metadata
    title = channel_name
    episode_title = None
    season_number = None
    episode_number = None
    synopsis = None
    image_url = None
    original_air_date = None
    category = None

    if channel:
        programs = await asyncio.to_thread(db.list_guide_programs, [channel["id"]], now - 300, now + 3600)
        for p in programs:
            if p["start_ts"] <= now < p["end_ts"]:
                title = p.get("title") or channel_name
                episode_title = p.get("episode_title")
                season_number = p.get("season_number")
                episode_number = p.get("episode_number")
                synopsis = p.get("synopsis")
                image_url = p.get("image_url")
                original_air_date = p.get("original_air_date")
                category = p.get("category")
                break

    recording_id = uuid.uuid4().hex
    capture = await capture_pipeline.start_capture(
        recording_id=recording_id,
        channel_number=channel_number,
        channel_name=channel_name,
        title=title,
        episode_title=episode_title,
        season_number=season_number,
        episode_number=episode_number,
        synopsis=synopsis,
        original_air_date=original_air_date,
        category=category,
        image_url=image_url,
        start_ts=now,
        end_ts=now + WATCH_MAX_DURATION_SECONDS,
        settings=settings,
        is_temporary=True,
    )
    if capture is None:
        await tuner_allocator.release_tuner(session_id)
        return None

    await capture_pipeline.add_viewer(recording_id, session_id)
    _sessions[session_id] = _WatchSession(session_id, recording_id, channel_number, now)
    return {"recording_id": recording_id, "session_id": session_id}


async def heartbeat_watch(session_id: str) -> bool:
    """Keep an active watch session alive. False if it no longer exists or has
    already been stopped, reaped, or its capture is gone."""
    session = _sessions.get(session_id)
    if session is None:
        return False
    if await capture_pipeline.get_active_capture(session.recording_id) is None:
        _sessions.pop(session_id, None)
        return False
    session.last_heartbeat_at = time.time()
    await asyncio.to_thread(db.update_recording, session.recording_id, last_heartbeat_at=session.last_heartbeat_at)
    return True


async def stop_watch(session_id: str) -> None:
    """This viewer closed the player. Detach their session; if their capture
    is still temporary (never promoted) and they were its last attached
    viewer, tear the whole thing down and discard what it captured."""
    session = _sessions.pop(session_id, None)
    if session is None:
        return

    remaining_viewers = await capture_pipeline.remove_viewer(session.recording_id, session_id)
    row = await asyncio.to_thread(db.get_recording, session.recording_id)
    if row is None or not row.get("is_temporary"):
        # Already gone, or promoted to a real recording that survives
        # independent of any viewer - only release this session's own token.
        await tuner_allocator.release_tuner(session_id)
        return

    if remaining_viewers <= 0:
        await finalize_capture_release(session.recording_id, session.channel_number)
    else:
        await tuner_allocator.release_tuner(session_id)


async def promote_watch(
    session_id: str,
    settings: dict[str, Any],
    title: str | None = None,
    episode_title: str | None = None,
    season_number: int | None = None,
    episode_number: int | None = None,
    synopsis: str | None = None,
    image_url: str | None = None,
    original_air_date: str | None = None,
    category: str | None = None,
    end_ts: float | None = None,
) -> bool:
    """Turn this session's in-progress auto-capture into a real recording: it
    survives every viewer (including this one) closing the player, keeps
    recording to end_ts (defaulting to its existing safety-cap end), and is
    no longer eligible for stop_watch/reap_stale_watches teardown.

    Acquires its own tuner token (keyed by recording_id, mirroring
    promote_existing_capture_for_schedule) so the channel's tuner stays
    reserved for the recording even after the originating viewer session
    stops - otherwise stop_watch's release of session_id would free the
    tuner out from under a still-running recording."""
    session = _sessions.get(session_id)
    if session is None:
        return False

    recording_id = session.recording_id
    row = await asyncio.to_thread(db.get_recording, recording_id)
    if row is None or not row.get("is_temporary"):
        return False
    if await capture_pipeline.get_active_capture(recording_id) is None:
        return False

    if not await tuner_allocator.acquire_tuner(recording_id, session.channel_number, settings):
        return False

    fields: dict[str, Any] = {"is_temporary": 0}
    if title is not None:
        fields["title"] = title
    if episode_title is not None:
        fields["episode_title"] = episode_title
    if season_number is not None:
        fields["season_number"] = season_number
    if episode_number is not None:
        fields["episode_number"] = episode_number
    if synopsis is not None:
        fields["synopsis"] = synopsis
    if image_url is not None:
        fields["image_url"] = image_url
    if original_air_date is not None:
        fields["original_air_date"] = original_air_date
    if category is not None:
        fields["category"] = category
    if end_ts is not None:
        fields["end_ts"] = end_ts

    await asyncio.to_thread(db.update_recording, recording_id, **fields)
    await capture_pipeline.update_active_capture(recording_id, **fields)

    return True


async def finalize_capture_release(recording_id: str, channel_number: str) -> None:
    """Force-tear-down a still-temporary capture: stop the writer, release
    every token attached to its channel (this viewer's session plus any other
    viewer sessions or the original capture-starting token — the whole
    capture is going away, not just one viewer's interest in it), and discard
    what it captured. Used both by stop_watch (last viewer left) and by
    DVREngine.tick() (safety-cap end_ts reached)."""
    await capture_pipeline.stop_capture(recording_id)
    await tuner_allocator.release_channel(channel_number)
    await delete_local_recording(recording_id)
    for sid in [sid for sid, s in _sessions.items() if s.recording_id == recording_id]:
        _sessions.pop(sid, None)


async def promote_existing_capture_for_schedule(
    capture: ActiveCapture,
    scheduled_id: str,
    rule_id: str | None,
    title: str,
    episode_title: str | None,
    end_ts: float,
    settings: dict[str, Any],
    season_number: int | None = None,
    episode_number: int | None = None,
    synopsis: str | None = None,
    image_url: str | None = None,
    original_air_date: str | None = None,
    category: str | None = None,
) -> bool:
    """A scheduled recording's start time arrived on a channel someone is
    already live-watching. Attach the schedule to that existing capture
    instead of starting a second tuner/ffmpeg for the same channel: promote
    it to a permanent (non-temporary) recording stamped with the schedule's
    identity, and extend its end_ts to the schedule's.

    Known limitation: if the viewer opened the channel after the schedule's
    intended start_ts, the resulting recording is missing that earlier
    portion - an accepted trade-off of "one writer per channel".
    """
    recording_id = capture.recording_id
    if not await tuner_allocator.acquire_tuner(recording_id, capture.channel_number, settings):
        return False

    update_fields: dict[str, Any] = {
        "is_temporary": 0,
        "scheduled_recording_id": scheduled_id,
        "title": title,
        "episode_title": episode_title,
        "end_ts": end_ts,
    }
    if season_number is not None:
        update_fields["season_number"] = season_number
    if episode_number is not None:
        update_fields["episode_number"] = episode_number
    if synopsis is not None:
        update_fields["synopsis"] = synopsis
    if image_url is not None:
        update_fields["image_url"] = image_url
    if original_air_date is not None:
        update_fields["original_air_date"] = original_air_date
    if category is not None:
        update_fields["category"] = category

    await asyncio.to_thread(
        db.update_recording,
        recording_id,
        **update_fields,
    )
    await capture_pipeline.update_active_capture(
        recording_id,
        is_temporary=False,
        scheduled_id=scheduled_id,
        rule_id=rule_id,
        **{k: v for k, v in update_fields.items() if k not in ("is_temporary", "scheduled_recording_id")},
    )
    with db._connect() as conn:
        conn.execute(
            "UPDATE scheduled_recordings SET status = 'in_progress', recording_id = ? WHERE id = ?",
            (recording_id, scheduled_id),
        )
    return True


async def reap_stale_watches() -> None:
    """Stop+discard any live-watch session whose client hasn't heartbeat-ed
    recently - the backstop for a tab that closed without the normal
    stop_watch call (crash, lost network, force-quit)."""
    cutoff = time.time() - WATCH_HEARTBEAT_TIMEOUT_SECONDS
    stale_session_ids = [sid for sid, session in _sessions.items() if session.last_heartbeat_at < cutoff]
    for session_id in stale_session_ids:
        session = _sessions.get(session_id)
        if session is not None:
            logger.info(
                "Reaping abandoned live-watch session [%s] on channel %s", session_id, session.channel_number
            )
        await stop_watch(session_id)
