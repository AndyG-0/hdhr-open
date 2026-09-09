"""HLS packaging sessions for native (Apple) clients and cast receivers.

`api/streaming.py`'s `/stream/{channel}` and `api/dvr.py`'s `/recording-stream`
both hand a single, unbounded, chunked `video/mp2t` HTTP response straight to
the caller — fine for the web frontend, which demuxes it in-browser via
mpegts.js + MSE, but AVFoundation (iOS/tvOS's only player) has no equivalent
and needs real HLS (a `.m3u8` playlist plus `.ts` segment files) instead. The
same sessions also serve a Chromecast/Google Cast receiver device casting
from the web or Android client, which needs real HLS for the same reason and
additionally can't authenticate via the normal session cookie/bearer header
(see `cast_token`/`verify_cast_token` in `api/hls.py`).

Unlike the existing routes, HLS is inherently multi-request: one session
creation, then an unbounded number of playlist/segment GETs that all have to
land on the same ffmpeg process's output directory. So instead of piping
ffmpeg's stdout directly into one HTTP response, an HLS session spawns ffmpeg
writing a rolling window of segments + a playlist into a per-session temp
directory, and every playlist/segment request just reads a file back out of
it. There is no single "disconnect" to poll for teardown (the polling trick
`api/streaming.py`'s `body()` generator uses) — so teardown here is instead
idle-timeout driven: every playlist/segment request counts as a heartbeat,
and a background reaper (registered the same way as
`app.dvr.builtin.watch.reap_stale_watches`) kills anything that's gone quiet.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import secrets
import shutil
import socket
import tempfile
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app import jobs
from app.async_utils import drain_stderr_tail, run_in_background, terminate_process
from app.config import HLS_SESSION_DIR
from app.subprocess_streaming import (
    DETAIL_REASON_CHARS,
    FFMPEG_NOT_FOUND_DETAIL,
    FFMPEG_STARTUP_TIMEOUT_SECONDS,
    STDERR_FLUSH_TIMEOUT_SECONDS,
    STDERR_TAIL_BYTES,
    build_ffmpeg_failure_detail,
    describe_ffmpeg_startup_failure,
)

logger = logging.getLogger(__name__)

# No playlist/segment request this long => assume the player is gone (closed
# app, crashed, lost network) and reap. Generous relative to how often a
# healthy HLS player actually re-fetches the playlist near the live edge.
HLS_IDLE_TIMEOUT_SECONDS = 300
# Safety cap on a single session's lifetime, independent of the idle reaper -
# belt and suspenders against a runaway ffmpeg if the reaper never runs for
# some reason. Mirrors app.dvr.builtin.watch.WATCH_MAX_DURATION_SECONDS.
HLS_MAX_SESSION_SECONDS = 4 * 3600
# Grace period before an untracked HLS_SESSION_DIR entry is treated as
# orphaned rather than a session still between allocate_session_dir() and
# being registered in _sessions - must safely exceed the worst case there
# (FFMPEG_STARTUP_TIMEOUT_SECONDS + HLS_CUSHION_TIMEOUT_SECONDS, ~35s).
ORPHAN_SESSION_DIR_GRACE_SECONDS = 120
# Backstop cadence - orphans should be rare now that create_session's own
# cleanup and the startup/shutdown sweeps cover the common leak paths; this
# only needs to catch what those miss.
ORPHAN_SESSION_DIR_SWEEP_INTERVAL_SECONDS = 300

_PLAYLIST_FILENAME = "stream.m3u8"
_SEGMENT_PATTERN = "segment%05d.ts"

_FFMPEG_TERMINATE_TIMEOUT_SECONDS = 5
_PLAYLIST_POLL_SECONDS = 0.2

# A playlist that's merely non-empty typically lists exactly one segment -
# AVPlayer joining with only that much live-edge cushion reliably logs
# CoreMediaErrorDomain -16832 ("stall danger") and stalls before the first
# frame. Apple's own HLS guidance is to keep ~3 segments of buffer available;
# `create_session` callers that build a live/growing-source HLS session (as
# opposed to a fixed on-demand file) pass this as `min_segments` so the
# session isn't handed to the client until that cushion actually exists.
HLS_READY_MIN_SEGMENTS = 3
# ffmpeg's HLS muxer only cuts a segment at the next keyframe at-or-after
# `-hls_time` - for a passthrough/copy live capture that's bound below by the
# source's actual keyframe interval, which can comfortably exceed the
# requested segment length. So accumulating HLS_READY_MIN_SEGMENTS can take
# meaningfully longer than min_segments * HLS_SEGMENT_SECONDS, and must not
# share FFMPEG_STARTUP_TIMEOUT_SECONDS (that budget exists to catch ffmpeg
# never producing *any* output at all, which is a much shorter bar). This is
# the separate, longer deadline granted once the first segment proves ffmpeg
# is healthy - mirrors the existing 20s tuner-lock budget
# (dvr.py's _LIVE_CAPTURE_READY_TIMEOUT_SECONDS).
HLS_CUSHION_TIMEOUT_SECONDS = 20
_EXTINF_RE = re.compile(rb"#EXTINF:")


def _segment_count(plist: Path) -> int:
    try:
        data = plist.read_bytes()
    except OSError:
        return 0
    return len(_EXTINF_RE.findall(data))


class HLSStartupError(Exception):
    """ffmpeg failed to produce a playlist before starting - the detail string
    is ready to hand straight to an HTTPException(502, detail=...)."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass
class HLSSession:
    session_id: str
    process: asyncio.subprocess.Process
    tmp_dir: Path
    created_at: float
    last_request_at: float
    label: str
    pump_task: asyncio.Task[None] | None = None
    pump_stop_event: asyncio.Event | None = None
    on_teardown: Callable[[], Awaitable[None]] | None = None
    cast_token: str | None = None
    _stderr_tail: bytearray = field(default_factory=bytearray)


_sessions: dict[str, HLSSession] = {}
# Guards only the _sessions dict itself, never held across an await into
# ffmpeg/process teardown - same discipline as watch.py's _lock.
_lock = asyncio.Lock()


def playlist_path(tmp_dir: Path) -> Path:
    return tmp_dir / _PLAYLIST_FILENAME


def segment_pattern(tmp_dir: Path) -> str:
    return str(tmp_dir / _SEGMENT_PATTERN)


def new_cast_token() -> str:
    """A random, unguessable capability token minted per cast session -
    same `secrets.token_urlsafe` convention app.auth uses for session/device
    ids, not a self-contained signed token (nothing else in this codebase
    does stateless/signed tokens)."""
    return secrets.token_urlsafe(24)


def cast_base_url(session_id: str, cast_token: str) -> str:
    """Path prefix an external cast receiver (Chromecast, Android's default
    Cast receiver) fetches the playlist/segments from, in place of the
    cookie/bearer-authenticated routes native clients use - see
    `verify_cast_token` in api/hls.py."""
    return f"/api/hls/{session_id}/{cast_token}/"


def cast_playlist_url(session_id: str, cast_token: str) -> str:
    return f"{cast_base_url(session_id, cast_token)}playlist.m3u8"


_LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1"}


def _lan_ip() -> str | None:
    """Best-effort address for this machine on its local network, found the
    standard way: "connecting" a UDP socket never actually sends a packet,
    it just asks the OS routing table which local interface it would use to
    reach that address - i.e. the real LAN interface (Wi-Fi/Ethernet), not
    loopback. Returns None (caller falls back to the unresolved relative
    path) if this machine has no route to the outside world at all, e.g. an
    offline dev box."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def cast_playlist_url_for_request(request_base_url: str, session_id: str, cast_token: str) -> str:
    """Same as `cast_playlist_url`, except resolved to an absolute,
    LAN-reachable URL when the incoming request's own host was
    "localhost"/"127.0.0.1". A Cast *receiver* is a separate physical device
    on the network - if the browser reached this server via localhost (the
    common single-machine dev setup), "localhost" in the URL handed to the
    receiver means the receiver itself, not this server, and its manifest
    fetch would always fail (see the CAST-1 bug report this fixes).

    Every other deployment shape (a real hostname/IP, or a container behind
    an operator-configured `PUBLIC_API_BASE_URL`) is left as the plain
    relative path exactly as before - the frontend's `PUBLIC_API_BASE_URL`
    already names a real, operator-chosen address in those cases, and this
    machine's own auto-detected interface (which could be a Docker bridge
    IP, wrong for that topology) must not override it.
    """
    relative = cast_playlist_url(session_id, cast_token)
    parts = urlsplit(request_base_url)
    if parts.hostname not in _LOCAL_HOSTNAMES:
        return relative
    lan_ip = _lan_ip()
    if lan_ip is None:
        return relative
    netloc = f"{lan_ip}:{parts.port}" if parts.port else lan_ip
    return urlunsplit((parts.scheme, netloc, relative, "", ""))


def allocate_session_dir() -> tuple[str, Path]:
    """Reserve a session id + its per-session temp directory up front, so a
    caller can build ffmpeg's playlist/segment path arguments (which must
    point inside that directory) before the process is actually spawned."""
    session_id = uuid.uuid4().hex
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"{session_id}-", dir=str(HLS_SESSION_DIR)))
    return session_id, tmp_dir


async def create_session(
    session_id: str,
    tmp_dir: Path,
    ffmpeg_args: list[str],
    *,
    label: str,
    stdin_pipe: bool = False,
    on_process_spawned: Callable[[asyncio.subprocess.Process], None] | None = None,
    min_segments: int = 1,
    on_teardown: Callable[[], Awaitable[None]] | None = None,
    cast_token: str | None = None,
) -> HLSSession:
    """Spawn ffmpeg (already built with output_format="hls" pointed at
    `tmp_dir`'s playlist/segment paths, per `allocate_session_dir`) and wait
    for it to produce a playable playlist. Raises HLSStartupError (safe to
    surface as a 502) if it doesn't.

    `on_process_spawned`, when given, fires synchronously right after the
    process exists and before the playlist-readiness wait below begins. A
    caller feeding this ffmpeg's stdin (e.g. a tail-follow pump reading a
    still-growing recording) must attach that feed here, not after
    `create_session` returns - the readiness wait blocks on ffmpeg actually
    producing a playlist, which it can never do while its stdin sits open
    and unfed.

    `min_segments` raises the readiness bar from "playlist exists" to
    "playlist lists at least this many segments" (see
    HLS_READY_MIN_SEGMENTS), still bounded by the same
    FFMPEG_STARTUP_TIMEOUT_SECONDS deadline. If ffmpeg exits on its own first
    (e.g. a short on-demand clip that will never reach `min_segments`), a
    non-empty playlist is still accepted - there's nothing left to wait for.

    `on_teardown`, when given, is awaited once from `teardown_session` after
    ffmpeg has been terminated and `tmp_dir` removed - the only teardown
    signal this session ever gets (idle-timeout or explicit stop), for a
    caller that needs to release some resource of its own (e.g. a capture's
    viewer token) exactly once the session is actually gone.

    Cleanup on any failure to reach a registered session - a spawn error, a
    failure to produce a playlist, `on_process_spawned` raising, or this
    coroutine's own task being cancelled while awaiting playlist readiness
    (e.g. the client disconnecting mid-startup) - is centralized in the
    `finally` below via the `registered` flag, rather than duplicated at each
    failure site, so no path can register neither a session nor cleanup.
    """
    process: asyncio.subprocess.Process | None = None
    registered = False
    try:
        try:
            process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                *ffmpeg_args,
                stdin=asyncio.subprocess.PIPE if stdin_pipe else asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise HLSStartupError(FFMPEG_NOT_FOUND_DETAIL) from exc

        if on_process_spawned is not None:
            on_process_spawned(process)

        assert process.stderr is not None

        now = time.time()
        session = HLSSession(
            session_id=session_id,
            process=process,
            tmp_dir=tmp_dir,
            created_at=now,
            last_request_at=now,
            label=label,
            on_teardown=on_teardown,
            cast_token=cast_token,
        )

        drain_done = asyncio.Event()
        run_in_background(
            drain_stderr_tail(process.stderr, session._stderr_tail, drain_done, tail_bytes=STDERR_TAIL_BYTES)
        )

        plist = playlist_path(tmp_dir)
        now0 = time.monotonic()
        # Two separate deadlines, not one shared budget: `startup_deadline` is
        # only about proving ffmpeg is alive and producing output at all (a
        # non-empty playlist), while `cushion_deadline` covers the (often much
        # longer) time it takes real segments to accumulate up to `min_segments`
        # once ffmpeg is already known-healthy - see HLS_CUSHION_TIMEOUT_SECONDS.
        startup_deadline = now0 + FFMPEG_STARTUP_TIMEOUT_SECONDS
        cushion_deadline = now0 + HLS_CUSHION_TIMEOUT_SECONDS
        while True:
            ready = plist.exists() and plist.stat().st_size > 0
            now = time.monotonic()
            if ready and (
                process.returncode is not None or _segment_count(plist) >= min_segments or now >= cushion_deadline
            ):
                break
            if not ready and (process.returncode is not None or now >= startup_deadline):
                break
            await asyncio.sleep(_PLAYLIST_POLL_SECONDS)

        if not plist.exists() or plist.stat().st_size == 0 or _segment_count(plist) == 0:
            cause, reason = await describe_ffmpeg_startup_failure(
                process,
                session._stderr_tail,
                drain_done,
                startup_timeout=FFMPEG_STARTUP_TIMEOUT_SECONDS,
                flush_timeout=STDERR_FLUSH_TIMEOUT_SECONDS,
            )
            logger.error("HLS session for %s failed to start: %s\nffmpeg output:\n%s", label, cause, reason or "(none)")
            detail = await build_ffmpeg_failure_detail(label, cause, reason, reason_chars=DETAIL_REASON_CHARS)
            raise HLSStartupError(detail)

        async with _lock:
            _sessions[session_id] = session
        registered = True
        logger.info("HLS session [%s] started for %s (dir=%s)", session_id, label, tmp_dir)
        return session
    finally:
        if not registered:
            if process is not None:
                run_in_background(terminate_process(process, timeout=_FFMPEG_TERMINATE_TIMEOUT_SECONDS))
            await asyncio.to_thread(shutil.rmtree, tmp_dir, ignore_errors=True)


async def touch(session_id: str) -> HLSSession | None:
    async with _lock:
        session = _sessions.get(session_id)
    if session is not None:
        session.last_request_at = time.time()
    return session


async def get(session_id: str) -> HLSSession | None:
    async with _lock:
        return _sessions.get(session_id)


async def attach_pump(session_id: str, pump_task: asyncio.Task[None], pump_stop_event: asyncio.Event) -> None:
    async with _lock:
        session = _sessions.get(session_id)
    if session is not None:
        session.pump_task = pump_task
        session.pump_stop_event = pump_stop_event


async def teardown_session(session_id: str) -> None:
    async with _lock:
        session = _sessions.pop(session_id, None)
    if session is None:
        return

    if session.pump_stop_event is not None:
        session.pump_stop_event.set()
    if session.pump_task is not None:
        with contextlib.suppress(Exception):
            await session.pump_task

    await terminate_process(session.process, timeout=_FFMPEG_TERMINATE_TIMEOUT_SECONDS)
    await asyncio.to_thread(shutil.rmtree, session.tmp_dir, ignore_errors=True)
    if session.on_teardown is not None:
        with contextlib.suppress(Exception):
            await session.on_teardown()
    logger.info("HLS session [%s] torn down (%s)", session_id, session.label)


async def teardown_all_sessions() -> None:
    """Best-effort teardown of every still-active session at process
    shutdown (a clean restart/deploy, not just a crash) - without this, a
    live session's ffmpeg child and directory outlive a graceful restart just
    as easily as a crash. Each id is torn down concurrently via
    teardown_session, with one id's failure isolated from the rest."""
    async with _lock:
        session_ids = list(_sessions.keys())
    if not session_ids:
        return
    results = await asyncio.gather(*(teardown_session(sid) for sid in session_ids), return_exceptions=True)
    for session_id, result in zip(session_ids, results, strict=True):
        if isinstance(result, Exception):
            logger.warning("Error tearing down HLS session [%s] at shutdown: %s", session_id, result)


async def reap_idle_sessions() -> None:
    """Backstop for a native client that never called .../stop (app killed,
    crashed, lost network) - the periodic job registered by `register()`."""
    now = time.time()
    async with _lock:
        stale = [
            sid
            for sid, s in _sessions.items()
            if now - s.last_request_at > HLS_IDLE_TIMEOUT_SECONDS or now - s.created_at > HLS_MAX_SESSION_SECONDS
        ]
    for session_id in stale:
        logger.info("Reaping idle/expired HLS session [%s]", session_id)
        await teardown_session(session_id)


async def sweep_session_dir_on_startup() -> None:
    """Unconditionally wipe every existing entry under HLS_SESSION_DIR at
    process boot. Safe unconditionally because `_sessions` is always empty at
    boot (in-memory only) and HLS session directories are ephemeral by design
    (see app.config's HLS_SESSION_DIR comment) - unlike
    DVREngine.recover_on_startup()'s DB-record reconciliation, there's no
    "still in progress" case to preserve here. Catches anything a prior
    crash (or a bug) left behind that reap_idle_sessions/teardown_session
    never got the chance to clean up."""
    if not HLS_SESSION_DIR.exists():
        return
    entries = await asyncio.to_thread(list, HLS_SESSION_DIR.iterdir())
    removed = 0
    for entry in entries:
        if entry.is_dir():
            await asyncio.to_thread(shutil.rmtree, entry, ignore_errors=True)
            removed += 1
    if removed:
        logger.info(
            "Startup sweep removed %d leftover HLS session director%s from %s",
            removed,
            "y" if removed == 1 else "ies",
            HLS_SESSION_DIR,
        )


async def sweep_orphaned_session_dirs() -> None:
    """Backstop: list HLS_SESSION_DIR's actual contents and remove any
    subdirectory that isn't tracked in `_sessions` and is older than
    ORPHAN_SESSION_DIR_GRACE_SECONDS. Directory names are
    f"{session_id}-{mkdtemp's random suffix}" (see allocate_session_dir), not
    the bare session_id, so matching is a startswith check rather than an
    exact key lookup. Meant to be rare given create_session's own cleanup and
    the startup/shutdown sweeps - this only needs to catch what those miss."""
    if not HLS_SESSION_DIR.exists():
        return
    async with _lock:
        tracked_prefixes = tuple(f"{sid}-" for sid in _sessions)
    now = time.time()
    entries = await asyncio.to_thread(list, HLS_SESSION_DIR.iterdir())
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith(tracked_prefixes):
            continue
        try:
            mtime = entry.stat().st_mtime
        except FileNotFoundError:
            continue
        if now - mtime < ORPHAN_SESSION_DIR_GRACE_SECONDS:
            continue
        logger.warning("Sweeping orphaned HLS session directory not tracked in memory: %s", entry)
        await asyncio.to_thread(shutil.rmtree, entry, ignore_errors=True)


def register(scheduler: AsyncIOScheduler) -> None:
    """Register the idle-session reaper and the orphaned-directory sweep with
    APScheduler. Kept independent of DVREngine.tick() - HLS packaging
    sessions aren't DVR captures."""
    jobs.register_scheduled_job(
        scheduler,
        job_id="hls_streaming_reap_idle_sessions",
        name="HLS idle session reaper",
        description="Tears down HLS packaging sessions that have gone quiet past the idle timeout.",
        func=reap_idle_sessions,
        trigger="interval",
        seconds=10,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    jobs.register_scheduled_job(
        scheduler,
        job_id="hls_streaming_sweep_orphaned_session_dirs",
        name="HLS orphaned session directory sweep",
        description="Removes leftover HLS session directories with no matching in-memory session.",
        func=sweep_orphaned_session_dirs,
        trigger="interval",
        seconds=ORPHAN_SESSION_DIR_SWEEP_INTERVAL_SECONDS,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


_SEGMENT_NAME_RE = re.compile(r"segment\d{5}\.ts")


def resolve_segment_path(session: HLSSession, name: str) -> Path | None:
    """Path-traversal guard: only a name matching the exact pattern ffmpeg was
    told to write (segmentNNNNN.ts) is ever joined onto the session's tmp_dir."""
    if not _SEGMENT_NAME_RE.fullmatch(name):
        return None
    return session.tmp_dir / name
