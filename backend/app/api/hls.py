"""HLS playlist/segment serving + session teardown for native (Apple) clients.

Session *creation* lives on the two callers that actually know how to build
an input (`api/streaming.py`'s `/hls/{channel_number}` for live channels,
`api/dvr.py`'s `/recording-stream-hls` for recordings) — this router only
serves back what `app.hls_streaming.create_session` already wrote to disk,
and tears a session down early on request.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response

from app import hls_streaming
from app.auth import get_current_user

router = APIRouter(prefix="/api/hls", tags=["hls"], dependencies=[Depends(get_current_user)])


async def _get_session_or_404(session_id: str) -> hls_streaming.HLSSession:
    session = await hls_streaming.touch(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="HLS session not found")
    return session


@router.get("/{session_id}/playlist.m3u8")
async def get_playlist(session_id: str):
    session = await _get_session_or_404(session_id)
    plist = hls_streaming.playlist_path(session.tmp_dir)
    if not plist.exists():
        raise HTTPException(status_code=404, detail="Playlist not available")
    return FileResponse(
        plist,
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/{session_id}/{name}")
async def get_segment(session_id: str, name: str):
    session = await _get_session_or_404(session_id)
    segment_path = hls_streaming.resolve_segment_path(session, name)
    if segment_path is None:
        raise HTTPException(status_code=400, detail="Invalid segment name")
    if not segment_path.exists():
        raise HTTPException(status_code=404, detail="Segment not available")
    return FileResponse(segment_path, media_type="video/mp2t")


@router.post("/{session_id}/stop")
async def stop_session(session_id: str):
    await hls_streaming.teardown_session(session_id)
    return Response(status_code=204)
