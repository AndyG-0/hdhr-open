"""Dual-engine recording-playback resolution shared by app.api.dvr_streaming's
routes: deciding whether a client-supplied recording URL/id belongs to this
app's builtin DVR engine (a local file) or the official HDHomeRun DVR engine
(a remote tuner-served URL, or a file on its local mount), and guarding
against path traversal while doing it. Kept out of app/api so the route
handlers in dvr_streaming.py stay thin wrappers around it - same split as
app.dvr.rule_engine for the recording-rules side.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from app import config
from app.dvr.builtin.capture import capture_pipeline
from app.integrations import hdhomerun_client
from app.storage import db

logger = logging.getLogger(__name__)


def resolve_target_media_url(
    settings: dict[str, Any],
    url: str,
    recording_id: str | None = None,
    provider: str | None = None,
) -> str:
    """Resolve a recording URL to either a local file path on disk or a remote HTTP URL.

    `provider` ("builtin" or "hdhomerun"), when the client supplies it, is
    trusted over the heuristics below - it comes from the same
    list_recordings() response that tagged the recording as builtin or
    official in the first place, so it authoritatively answers "does this
    recording belong to our own DVR" without having to infer it from whether
    an official DVR happens to also be configured.
    """
    if url:
        # A local path is only ever trusted if it resolves inside
        # RECORDINGS_DIR - client-supplied `url` otherwise reaches ffmpeg,
        # ffprobe, and FileResponse below, so an unconstrained path here is
        # an arbitrary local file read (e.g. `url=backend/secret.key`).
        # Legitimate local playback URLs always come from list_recordings(),
        # which only ever hands out paths already confined to
        # RECORDINGS_DIR; a remote HDHomeRun-DVR URL never matches this
        # branch since Path(url).exists() is false for an http(s):// value.
        resolved = Path(url).resolve()
        p: Path | None
        try:
            resolved.relative_to(config.RECORDINGS_DIR.resolve())
            p = resolved
        except ValueError:
            p = None
        if p is not None and p.exists() and p.is_file():
            return str(p)

    if recording_id:
        rec = db.get_recording(recording_id)
        if rec:
            file_path = rec.get("file_path")
            if file_path:
                p = Path(file_path)
                if p.exists() or capture_pipeline.is_capture_active(recording_id):
                    # An active capture's file may not exist yet - the writer
                    # ffmpeg is registered before it locks the tuner and flushes
                    # its first bytes (see CapturePipeline.start_capture). That's
                    # expected for live TV and just-started recordings; callers
                    # already handle readiness via _wait_for_live_capture_data.
                    return str(p)
            # This recording_id names a builtin-DVR recording (found in our
            # own database), not a remote-engine one - whether its file_path
            # is unset or points at a file no longer on disk, falling through
            # to hdhomerun_client.resolve_recording_url below would treat
            # that local path/ID as a tuner/DVR-relative URL fragment and
            # concatenate it onto http://{dvr_host}:{dvr_port}/, producing a
            # nonsensical URL that ffmpeg then fails to open with an opaque
            # 404. Raise a clear, specific error instead.
            raise HTTPException(
                status_code=404,
                detail=f"Recording file no longer exists on disk: {file_path or '(no file recorded)'}",
            )

        # No local builtin-DVR row for this ID. If the client told us this is
        # a builtin recording, that's authoritative - never fall through to
        # the official DVR, no matter whether one happens to be configured;
        # doing so previously routed builtin recordings the client couldn't
        # find locally (e.g. a stale/cached id) to the HDHomeRun DVR server
        # and produced an opaque 404 from *that* server instead of a clear
        # local one. Without a provider hint (older clients), fall back to
        # the old heuristic: list_recordings() only ever hands a client an
        # official-HDHomeRun-DVR recording_id when
        # hdhomerun_client.is_dvr_configured() is true, so if it's false here
        # this recording_id can't legitimately be one either.
        if provider == "builtin" or (provider is None and not hdhomerun_client.is_dvr_configured(settings)):
            raise HTTPException(
                status_code=404,
                detail=f"Recording not found: {recording_id}",
            )

    try:
        return hdhomerun_client.resolve_recording_url(settings, url)
    except hdhomerun_client.HDHomeRunError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def resolve_local_media_path_for_edl(
    target_url: str, recording_id: str, provider: str | None, settings: dict[str, Any], hdhomerun_filename: str | None
) -> Path | None:
    """The local file comskip would have written `<file>.edl` next to, if
    any - `target_url` itself is only ever that file for a builtin
    recording (an official HDHomeRun DVR recording's `target_url` is
    always the remote HTTP URL it's streamed from). For a HDHomeRun
    recording, resolve it instead via `hdhomerun_filename` (see
    app.api.dvr_streaming._resolve_hdhomerun_edl_filename), joined onto the
    admin-configured local mount of that engine's storage.
    """
    if provider != "hdhomerun":
        p = Path(target_url)
        found = p.is_file()
        logger.info(
            "EDL lookup for %s: provider=%r treated as local path %s (exists=%s)",
            recording_id,
            provider,
            p,
            found,
        )
        return p if found else None

    recordings_path = settings.get("dvr_recordings_path")
    if not recordings_path:
        logger.info("EDL lookup for %s: provider=hdhomerun but dvr_recordings_path is not configured", recording_id)
        return None
    if not hdhomerun_filename:
        logger.info(
            "EDL lookup for %s: provider=hdhomerun but no DVR filename could be found for this recording_id"
            " (not tracked locally, and not in the DVR engine's current recordings list)",
            recording_id,
        )
        return None

    from app.dvr.builtin.comskip import resolve_hdhomerun_local_path

    path = resolve_hdhomerun_local_path(recordings_path, hdhomerun_filename)
    resolved = path is not None and path.is_file()
    logger.info(
        "EDL lookup for %s: filename=%r -> resolved local path=%s (exists=%s)",
        recording_id,
        hdhomerun_filename,
        path,
        resolved,
    )
    return path if resolved else None
