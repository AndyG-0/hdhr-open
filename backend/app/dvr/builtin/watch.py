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
# Guards every read/write of _sessions itself (not the _WatchSession objects'
# fields). Currently safe without one - no `await` sits between a get and a
# mutate anywhere below - but that's fragile against future edits, so this
# follows the same discipline as TunerAllocator's self._lock. Scope each
# `async with _lock` to just the dict operation; never hold it across an
# await into capture_pipeline/tuner_allocator/stop_watch, which would
# deadlock against a caller already holding it (the lock isn't reentrant).
_lock = asyncio.Lock()


async def _build_capture_for_channel(channel_number: str, settings: dict[str, Any], now: float) -> ActiveCapture | None:
    """Look up channel_number's current airing (for rich metadata) and start
    a temporary capture for it. Deliberately does not touch tuner_allocator -
    reservation is the caller's responsibility (see start_watch and
    start_fallback_capture, which reserve it differently)."""
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
    return await capture_pipeline.start_capture(
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


async def start_watch(channel_number: str, settings: dict[str, Any]) -> dict[str, str] | None:
    """Start (or attach to) a live-watch session for channel_number. Returns
    {"recording_id", "session_id"}, or None if no tuner is available and no
    capture already exists for this channel - callers should fall back to
    plain live streaming (no pause/rewind) in that case."""
    session_id = uuid.uuid4().hex
    now = time.time()

    async def _create_capture() -> ActiveCapture | None:
        if not await tuner_allocator.acquire_tuner(session_id, channel_number, settings):
            return None
        capture = await _build_capture_for_channel(channel_number, settings, now)
        if capture is None:
            await tuner_allocator.release_tuner(session_id)
        return capture

    capture, created = await capture_pipeline.get_or_start_capture(channel_number, _create_capture)
    if capture is None:
        return None

    if not created and not await tuner_allocator.acquire_tuner(session_id, channel_number, settings):
        return None

    await capture_pipeline.add_viewer(capture.recording_id, session_id)
    async with _lock:
        _sessions[session_id] = _WatchSession(session_id, capture.recording_id, channel_number, now)
    return {"recording_id": capture.recording_id, "session_id": session_id}


async def heartbeat_watch(session_id: str) -> bool:
    """Keep an active watch session alive. False if it no longer exists or has
    already been stopped, reaped, or its capture is gone."""
    async with _lock:
        session = _sessions.get(session_id)
    if session is None:
        return False
    if await capture_pipeline.get_active_capture(session.recording_id) is None:
        async with _lock:
            _sessions.pop(session_id, None)
        return False
    session.last_heartbeat_at = time.time()
    await asyncio.to_thread(db.update_recording, session.recording_id, last_heartbeat_at=session.last_heartbeat_at)
    return True


async def _release_viewer(recording_id: str, channel_number: str, viewer_token: str) -> None:
    """Detach viewer_token from recording_id's capture; if it's still
    temporary (never promoted) and this was its last attached viewer, tear
    the whole thing down and discard what it captured. Shared by stop_watch
    (the watch-session path) and release_fallback_capture (the direct-HLS
    fallback path, see app.api.streaming.stream_channel_hls) - both attach
    exactly one token per viewer to a capture the same way; they only differ
    in how that capture got started."""
    remaining_viewers = await capture_pipeline.remove_viewer(recording_id, viewer_token)
    row = await asyncio.to_thread(db.get_recording, recording_id)
    if row is None or not row.get("is_temporary"):
        # Already gone, or promoted to a real recording that survives
        # independent of any viewer - only release this viewer's own token.
        await tuner_allocator.release_tuner(viewer_token)
        return

    if remaining_viewers <= 0:
        await finalize_capture_release(recording_id, channel_number)
    else:
        await tuner_allocator.release_tuner(viewer_token)


async def stop_watch(session_id: str) -> None:
    """This viewer closed the player. Detach their session; if their capture
    is still temporary (never promoted) and they were its last attached
    viewer, tear the whole thing down and discard what it captured."""
    async with _lock:
        session = _sessions.pop(session_id, None)
    if session is None:
        return
    await _release_viewer(session.recording_id, session.channel_number, session_id)


async def start_fallback_capture(channel_number: str, settings: dict[str, Any], viewer_token: str) -> str | None:
    """Start (or attach to) a capture for channel_number on behalf of the
    direct-HLS fallback path (see app.api.streaming.stream_channel_hls),
    deliberately WITHOUT going through tuner_allocator's admission gate
    first - that gate is exactly what the client's primary path
    (start_watch) already consulted and rejected before falling back here,
    so re-checking it would just reproduce the same rejection. This lets the
    hardware/ffmpeg itself be the arbiter of whether another stream can
    actually be served, same as this endpoint always has - the only change
    is that a successful capture now backs real captions/pause/rewind
    instead of a bare unmanaged ffmpeg pipe.

    Still makes a best-effort tuner_allocator registration afterward so its
    bookkeeping stays as accurate as possible - but a failure there is only
    logged, never treated as a reason to fail this call, since by definition
    the allocator already believes there's no room.

    Returns recording_id, or None if even an unmanaged capture couldn't be
    started (e.g. ffmpeg unspawnable, tuner not configured)."""
    now = time.time()
    capture, _created = await capture_pipeline.get_or_start_capture(
        channel_number, lambda: _build_capture_for_channel(channel_number, settings, now)
    )
    if capture is None:
        return None

    if not await tuner_allocator.acquire_tuner(viewer_token, channel_number, settings):
        logger.info(
            "Fallback capture on channel %s started without a tuner_allocator token "
            "(allocator already at capacity) - hardware served it anyway",
            channel_number,
        )

    await capture_pipeline.add_viewer(capture.recording_id, viewer_token)
    return capture.recording_id


async def release_fallback_capture(recording_id: str, channel_number: str, viewer_token: str) -> None:
    """Counterpart to start_fallback_capture, called when its direct-HLS
    packaging session is torn down (see hls_streaming.HLSSession.on_teardown)
    - the only teardown signal this path has, since unlike watch sessions
    there's no heartbeat contract here."""
    await _release_viewer(recording_id, channel_number, viewer_token)


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
) -> str | None:
    """Turn this session's in-progress auto-capture into a real recording: it
    survives every viewer (including this one) closing the player, keeps
    recording to end_ts (defaulting to its existing safety-cap end), and is
    no longer eligible for stop_watch/reap_stale_watches teardown. Returns
    the promoted recording_id, or None if the session/capture couldn't be
    promoted.

    Acquires its own tuner token (keyed by recording_id, mirroring
    promote_existing_capture_for_schedule) so the channel's tuner stays
    reserved for the recording even after the originating viewer session
    stops - otherwise stop_watch's release of session_id would free the
    tuner out from under a still-running recording."""
    async with _lock:
        session = _sessions.get(session_id)
    if session is None:
        return None

    recording_id = session.recording_id
    row = await asyncio.to_thread(db.get_recording, recording_id)
    if row is None or not row.get("is_temporary"):
        return None
    if await capture_pipeline.get_active_capture(recording_id) is None:
        return None

    if not await tuner_allocator.acquire_tuner(recording_id, session.channel_number, settings):
        return None

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

    return recording_id


async def finalize_capture_release(recording_id: str, channel_number: str) -> None:
    """Force-tear-down a still-temporary capture: stop the writer, release
    every token attached to its channel (this viewer's session plus any other
    viewer sessions or the original capture-starting token — the whole
    capture is going away, not just one viewer's interest in it), and discard
    what it captured. Used both by stop_watch (last viewer left) and by
    DVREngine.tick() (safety-cap end_ts reached)."""
    await capture_pipeline.stop_capture(recording_id)
    await tuner_allocator.release_channel(channel_number)
    await delete_local_recording(recording_id, reason="discarded ephemeral watch-buffer capture (never promoted to a saved recording)")
    async with _lock:
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
    await asyncio.to_thread(db.mark_scheduled_recording_in_progress, scheduled_id, recording_id)
    return True


async def reap_stale_watches() -> None:
    """Stop+discard any live-watch session whose client hasn't heartbeat-ed
    recently - the backstop for a tab that closed without the normal
    stop_watch call (crash, lost network, force-quit)."""
    cutoff = time.time() - WATCH_HEARTBEAT_TIMEOUT_SECONDS
    async with _lock:
        stale_session_ids = [sid for sid, session in _sessions.items() if session.last_heartbeat_at < cutoff]
    for session_id in stale_session_ids:
        async with _lock:
            session = _sessions.get(session_id)
        if session is not None:
            logger.info(
                "Reaping abandoned live-watch session [%s] on channel %s", session_id, session.channel_number
            )
        await stop_watch(session_id)
