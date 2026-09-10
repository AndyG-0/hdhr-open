from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.auth import SESSION_COOKIE_NAME, get_auth_token_by_hash, get_current_user, get_session, get_user, hash_token

logger = logging.getLogger(__name__)

# Unlike dvr.py/streaming.py/watch.py, this router cannot declare `dependencies=` at the
# APIRouter level: FastAPI applies router-level dependencies to `@router.websocket(...)`
# routes too, but a websocket scope can't satisfy get_current_user's `Request` parameter
# (it errors at dependency-resolution time). So auth is applied per-route below for the
# REST endpoints, and the WebSocket endpoint authenticates itself explicitly instead.
router = APIRouter(prefix="/api/syncplay", tags=["syncplay"])

# 6-character room codes using uppercase letters and digits, omitting ambiguous characters (0, O, 1, I)
_ROOM_CODE_CHARS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_EMPTY_ROOM_GRACE_PERIOD_SECONDS = 300.0  # 5 minutes


def _generate_room_code() -> str:
    return "".join(random.choices(_ROOM_CODE_CHARS, k=6))


class SyncPlayContent(BaseModel):
    type: str = Field(description="'channel' or 'recording'")
    id: str = Field(description="Channel number or recording ID")
    title: str = Field(default="", description="Media title")
    channel_number: str | None = Field(default=None, description="Optional channel number")
    play_url: str | None = Field(default=None, description="Optional playback or stream URL")


class SyncPlayPlaybackState(BaseModel):
    is_playing: bool = False
    position: float = 0.0
    playback_rate: float = 1.0
    updated_at: float = Field(default_factory=time.time)


class SyncPlayParticipant(BaseModel):
    session_id: str
    user_id: str | None = None
    user_name: str = "Viewer"
    avatar: str | None = None
    is_host: bool = False
    is_ready: bool = True
    ping_ms: float = 0.0
    position: float = 0.0
    last_seen: float = Field(default_factory=time.time)


class SyncPlayRoomSummary(BaseModel):
    room_code: str
    created_at: float
    host_session_id: str | None
    content: SyncPlayContent
    playback_state: SyncPlayPlaybackState
    participants: list[SyncPlayParticipant]


class CreateRoomRequest(BaseModel):
    content: SyncPlayContent
    user_name: str | None = None


class CreateRoomResponse(BaseModel):
    room_code: str
    room: SyncPlayRoomSummary


class SyncPlayRoom:
    def __init__(self, room_code: str, content: SyncPlayContent, host_session_id: str | None = None):
        self.room_code = room_code
        self.created_at = time.time()
        self.content = content
        self.host_session_id = host_session_id
        self.playback_state = SyncPlayPlaybackState(
            is_playing=False, position=0.0, playback_rate=1.0, updated_at=time.time()
        )
        self.participants: dict[str, SyncPlayParticipant] = {}
        self.connections: dict[str, WebSocket] = {}
        self.empty_since: float | None = None
        self._lock = asyncio.Lock()

    def get_authoritative_position(self) -> float:
        now = time.time()
        if self.playback_state.is_playing:
            elapsed = (now - self.playback_state.updated_at) * self.playback_state.playback_rate
            return max(0.0, self.playback_state.position + elapsed)
        return self.playback_state.position

    async def add_participant(
        self,
        session_id: str,
        user_name: str,
        user_id: str | None,
        avatar: str | None,
        websocket: WebSocket,
    ) -> SyncPlayParticipant:
        async with self._lock:
            self.empty_since = None
            is_host = self.host_session_id is None or self.host_session_id == session_id
            if is_host:
                self.host_session_id = session_id

            participant = SyncPlayParticipant(
                session_id=session_id,
                user_id=user_id,
                user_name=user_name,
                avatar=avatar,
                is_host=is_host,
                is_ready=True,
                ping_ms=0.0,
                position=self.get_authoritative_position(),
                last_seen=time.time(),
            )
            self.participants[session_id] = participant
            self.connections[session_id] = websocket
            return participant

    async def remove_participant(self, session_id: str) -> str | None:
        """Removes participant and elects new host if host left. Returns new host_session_id if changed."""
        async with self._lock:
            self.participants.pop(session_id, None)
            self.connections.pop(session_id, None)

            if not self.participants:
                self.empty_since = time.time()
                self.host_session_id = None
                return None

            new_host_id = None
            if self.host_session_id == session_id:
                # Elect the first remaining participant as host
                next_host_session_id = next(iter(self.participants))
                self.host_session_id = next_host_session_id
                self.participants[next_host_session_id].is_host = True
                new_host_id = next_host_session_id

            return new_host_id

    async def set_host(self, target_session_id: str) -> bool:
        async with self._lock:
            if target_session_id not in self.participants:
                return False
            for sid, p in self.participants.items():
                p.is_host = (sid == target_session_id)
            self.host_session_id = target_session_id
            return True

    async def update_playback(
        self,
        action: str,
        position: float | None = None,
        playback_rate: float | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            now = time.time()
            if action == "play":
                pos = position if position is not None else self.get_authoritative_position()
                rate = playback_rate if playback_rate is not None else self.playback_state.playback_rate
                self.playback_state = SyncPlayPlaybackState(
                    is_playing=True,
                    position=pos,
                    playback_rate=rate,
                    updated_at=now,
                )
            elif action == "pause":
                pos = position if position is not None else self.get_authoritative_position()
                self.playback_state = SyncPlayPlaybackState(
                    is_playing=False,
                    position=pos,
                    playback_rate=1.0,
                    updated_at=now,
                )
            elif action == "seek":
                pos = position if position is not None else 0.0
                self.playback_state = SyncPlayPlaybackState(
                    is_playing=self.playback_state.is_playing,
                    position=pos,
                    playback_rate=self.playback_state.playback_rate,
                    updated_at=now,
                )

            return {
                "type": "playback_update",
                "action": action,
                "position": self.playback_state.position,
                "is_playing": self.playback_state.is_playing,
                "playback_rate": self.playback_state.playback_rate,
                "server_time": now,
            }

    async def update_content(self, content: SyncPlayContent) -> None:
        async with self._lock:
            self.content = content
            self.playback_state = SyncPlayPlaybackState(
                is_playing=False,
                position=0.0,
                playback_rate=1.0,
                updated_at=time.time(),
            )

    async def broadcast(self, message: dict[str, Any], exclude_session_id: str | None = None) -> None:
        async with self._lock:
            dead_connections = []
            for sid, ws in list(self.connections.items()):
                if exclude_session_id and sid == exclude_session_id:
                    continue
                try:
                    await ws.send_json(message)
                except Exception as e:
                    logger.debug("Failed to send message to session %s: %s", sid, e)
                    dead_connections.append(sid)

            for dead_sid in dead_connections:
                self.connections.pop(dead_sid, None)

    def to_summary(self) -> SyncPlayRoomSummary:
        return SyncPlayRoomSummary(
            room_code=self.room_code,
            created_at=self.created_at,
            host_session_id=self.host_session_id,
            content=self.content,
            playback_state=SyncPlayPlaybackState(
                is_playing=self.playback_state.is_playing,
                position=self.get_authoritative_position(),
                playback_rate=self.playback_state.playback_rate,
                updated_at=self.playback_state.updated_at,
            ),
            participants=list(self.participants.values()),
        )


class SyncPlayHub:
    """Room state is in-memory only, by design — consistent with the rest of
    the engine's crash-recovery model (see `dvr/builtin/watch.py`'s session
    registry for the same rationale): on a process restart there's no
    meaningful state to persist for viewers who are no longer connected
    anyway. A client reconnecting with a stale room code after a restart
    gets the same `4004` close it would get for a simply-invalid code — that
    is the intended recovery signal, not a bug to be papered over with
    silent reconnection.
    """

    def __init__(self):
        self.rooms: dict[str, SyncPlayRoom] = {}
        self._lock = asyncio.Lock()

    async def create_room(self, content: SyncPlayContent, host_session_id: str | None = None) -> SyncPlayRoom:
        async with self._lock:
            self.reap_stale_rooms()
            for _ in range(20):
                code = _generate_room_code()
                if code not in self.rooms:
                    room = SyncPlayRoom(code, content, host_session_id)
                    self.rooms[code] = room
                    return room
            # Fallback if collision
            code = uuid.uuid4().hex[:6].upper()
            room = SyncPlayRoom(code, content, host_session_id)
            self.rooms[code] = room
            return room

    def get_room(self, room_code: str) -> SyncPlayRoom | None:
        code = room_code.strip().upper()
        return self.rooms.get(code)

    def reap_stale_rooms(self) -> None:
        now = time.time()
        to_delete = []
        for code, room in self.rooms.items():
            if room.empty_since is not None and (now - room.empty_since > _EMPTY_ROOM_GRACE_PERIOD_SECONDS):
                to_delete.append(code)
        for code in to_delete:
            self.rooms.pop(code, None)


hub = SyncPlayHub()


async def _resolve_ws_identity(websocket: WebSocket, token: str | None = None) -> tuple[str, str, str | None] | None:
    """Resolves (user_id, display_name, avatar) for an authenticated caller from WebSocket
    cookies or a token query parameter, or None if neither resolves to a real user.

    Router-level `dependencies` (used for the REST routes in this module) do not apply to
    `@router.websocket(...)` routes, so this WebSocket endpoint must authenticate explicitly.
    """
    # 1. Bearer / Query Token
    if token:
        token_hash = hash_token(token)
        token_row = await asyncio.to_thread(get_auth_token_by_hash, token_hash)
        if token_row:
            user = await asyncio.to_thread(get_user, token_row["user_id"])
            if user:
                return user["id"], user.get("name", "Viewer"), user.get("avatar")

    # 2. Session cookie
    session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        session = await asyncio.to_thread(get_session, session_id)
        if session:
            user = await asyncio.to_thread(get_user, session["user_id"])
            if user:
                return user["id"], user.get("name", "Viewer"), user.get("avatar")

    return None


@router.post("/rooms", response_model=CreateRoomResponse, dependencies=[Depends(get_current_user)])
async def create_room(payload: CreateRoomRequest, request: Request):
    """Creates a new watch room with the provided content metadata."""
    room = await hub.create_room(payload.content)
    return CreateRoomResponse(room_code=room.room_code, room=room.to_summary())


@router.get("/rooms/{room_code}", response_model=SyncPlayRoomSummary, dependencies=[Depends(get_current_user)])
async def get_room(room_code: str):
    """Fetches watch room details and active participant status."""
    room = hub.get_room(room_code)
    if not room:
        raise HTTPException(status_code=404, detail="Watch room not found")
    return room.to_summary()


@router.get("/rooms", response_model=list[SyncPlayRoomSummary], dependencies=[Depends(get_current_user)])
async def list_rooms():
    """Lists active watch rooms."""
    hub.reap_stale_rooms()
    return [room.to_summary() for room in hub.rooms.values() if not room.empty_since]


@router.websocket("/ws/{room_code}")
async def syncplay_websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    token: str | None = Query(default=None),
    user_name: str | None = Query(default=None),
):
    """WebSocket endpoint for real-time SyncPlay synchronization."""
    identity = await _resolve_ws_identity(websocket, token=token)
    if identity is None:
        # 4401: custom close code for "Unauthorized" (mirrors the 4004 "Watch room not
        # found" convention below). Checked before the room lookup so an unauthenticated
        # caller can't use this endpoint to probe whether a room code exists.
        await websocket.close(code=4401, reason="Unauthorized")
        return

    room = hub.get_room(room_code)
    if not room:
        await websocket.close(code=4004, reason="Watch room not found")
        return

    await websocket.accept()

    user_id, display_name, avatar = identity
    if user_name:
        display_name = user_name

    session_id = uuid.uuid4().hex[:8]
    participant = await room.add_participant(
        session_id=session_id,
        user_name=display_name,
        user_id=user_id,
        avatar=avatar,
        websocket=websocket,
    )

    logger.info("SyncPlay session %s (%s) joined room %s", session_id, display_name, room.room_code)

    # Send initial room state to new participant
    await websocket.send_json({
        "type": "room_state",
        "room": room.to_summary().model_dump(),
        "your_session_id": session_id,
    })

    # Notify all other participants
    await room.broadcast(
        {
            "type": "participant_joined",
            "participant": participant.model_dump(),
        },
        exclude_session_id=session_id,
    )

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "ping":
                client_time = data.get("client_time", 0.0)
                await websocket.send_json({
                    "type": "pong",
                    "client_time": client_time,
                    "server_time": time.time(),
                })

            elif msg_type == "progress":
                pos = float(data.get("position", 0.0))
                is_ready = bool(data.get("is_ready", True))
                ping_ms = float(data.get("ping_ms", 0.0))
                if session_id in room.participants:
                    p = room.participants[session_id]
                    p.position = pos
                    p.is_ready = is_ready
                    p.ping_ms = ping_ms
                    p.last_seen = time.time()
                    # Broadcast presence updates to peers when progress is received
                    await room.broadcast(
                        {
                            "type": "participant_updated",
                            "participant": p.model_dump(),
                        },
                        exclude_session_id=session_id,
                    )

            elif msg_type in ("play", "pause", "seek"):
                position = data.get("position")
                pos_float = float(position) if position is not None else None
                rate = float(data.get("playback_rate", 1.0))
                update_msg = await room.update_playback(msg_type, position=pos_float, playback_rate=rate)
                update_msg["triggered_by"] = session_id
                # Broadcast update to all participants (including sender to calibrate server_time)
                await room.broadcast(update_msg)

            elif msg_type == "change_content":
                if room.host_session_id == session_id:
                    new_content = SyncPlayContent(**data.get("content", {}))
                    await room.update_content(new_content)
                    await room.broadcast({
                        "type": "content_changed",
                        "content": new_content.model_dump(),
                        "room": room.to_summary().model_dump(),
                    })

            elif msg_type == "transfer_host":
                if room.host_session_id == session_id:
                    target_id = data.get("target_session_id")
                    if target_id and await room.set_host(target_id):
                        await room.broadcast({
                            "type": "host_changed",
                            "new_host_session_id": target_id,
                            "room": room.to_summary().model_dump(),
                        })

            elif msg_type == "leave":
                break

    except WebSocketDisconnect:
        logger.info("SyncPlay session %s disconnected from room %s", session_id, room.room_code)
    except Exception as e:
        logger.warning("SyncPlay WebSocket error for session %s: %s", session_id, e)
    finally:
        new_host_id = await room.remove_participant(session_id)
        logger.info("SyncPlay session %s left room %s", session_id, room.room_code)

        # Broadcast participant left
        await room.broadcast({
            "type": "participant_left",
            "session_id": session_id,
            "new_host_session_id": new_host_id,
        })
