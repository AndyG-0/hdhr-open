"""HLS playlist/segment serving + session teardown for native (Apple)
clients and cast receivers.

Session *creation* lives on the two callers that actually know how to build
an input (`api/streaming.py`'s `/hls/{channel_number}` for live channels,
`api/dvr.py`'s `/recording-stream-hls` for recordings) — this router only
serves back what `app.hls_streaming.create_session` already wrote to disk,
and tears a session down early on request.

Two parallel sets of GET routes serve the same playlist/segment files under
different auth:
- `/{session_id}/playlist.m3u8` and `/{session_id}/{name}` require the
  normal `get_current_user` session cookie/bearer auth — used by native
  Apple playback and by the *sender* (browser tab, Android app) itself.
- `/{session_id}/{cast_token}/playlist.m3u8` and
  `/{session_id}/{cast_token}/{name}` are gated by `verify_cast_token`
  instead, for a Chromecast/Google Cast *receiver* device fetching the
  manifest directly — it can't send a session cookie or bearer header, so
  `for_cast=True` session creation (`api/streaming.py`, `api/dvr.py`) mints
  a per-session capability token embedded in this path instead (see
  `hls_streaming.new_cast_token`/`cast_playlist_url`). There is no
  cast-token variant of `/stop`: the sender ends the session through its
  own already-authenticated call to the cookie/bearer-gated route below,
  never the receiver device.
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from app import hls_streaming
from app.auth import get_current_user

router = APIRouter(prefix="/api/hls", tags=["hls"])


async def _get_session_or_404(session_id: str) -> hls_streaming.HLSSession:
    session = await hls_streaming.touch(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="HLS session not found")
    return session


async def verify_cast_token(session_id: str, cast_token: str) -> hls_streaming.HLSSession:
    session = await hls_streaming.touch(session_id)
    if session is None or session.cast_token is None or not hmac.compare_digest(cast_token, session.cast_token):
        # Same 404 (not 401/403) as a missing session_id - a wrong/expired
        # token shouldn't reveal whether the session_id itself is real.
        raise HTTPException(status_code=404, detail="HLS session not found")
    return session


def _playlist_response(session: hls_streaming.HLSSession) -> FileResponse:
    plist = hls_streaming.playlist_path(session.tmp_dir)
    if not plist.exists():
        raise HTTPException(status_code=404, detail="Playlist not available")
    return FileResponse(
        plist,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache"},
    )


def _segment_response(session: hls_streaming.HLSSession, name: str) -> FileResponse:
    segment_path = hls_streaming.resolve_segment_path(session, name)
    if segment_path is None:
        raise HTTPException(status_code=400, detail="Invalid segment name")
    if not segment_path.exists():
        raise HTTPException(status_code=404, detail="Segment not available")
    return FileResponse(segment_path, media_type="video/mp2t")


@router.get("/{session_id}/playlist.m3u8", dependencies=[Depends(get_current_user)])
async def get_playlist(session_id: str):
    return _playlist_response(await _get_session_or_404(session_id))


@router.get("/{session_id}/{name}", dependencies=[Depends(get_current_user)])
async def get_segment(session_id: str, name: str):
    return _segment_response(await _get_session_or_404(session_id), name)


@router.post("/{session_id}/heartbeat", dependencies=[Depends(get_current_user)])
async def heartbeat(session_id: str):
    await _get_session_or_404(session_id)
    return Response(status_code=204)


@router.post("/{session_id}/stop", dependencies=[Depends(get_current_user)])
async def stop_session(session_id: str):
    await hls_streaming.teardown_session(session_id)
    return Response(status_code=204)


@router.post("/{session_id}/{cast_token}/heartbeat")
async def heartbeat_for_cast(session: hls_streaming.HLSSession = Depends(verify_cast_token)):
    return Response(status_code=204)


@router.get("/{session_id}/{cast_token}/playlist.m3u8")
async def get_playlist_for_cast(session: hls_streaming.HLSSession = Depends(verify_cast_token)):
    return _playlist_response(session)


@router.get("/{session_id}/{cast_token}/{name}")
async def get_segment_for_cast(name: str, session: hls_streaming.HLSSession = Depends(verify_cast_token)):
    return _segment_response(session, name)
