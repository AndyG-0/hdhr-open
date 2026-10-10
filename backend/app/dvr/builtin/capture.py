"""FFmpeg capture pipeline for the builtin DVR engine.

Stream-copies MPEG-TS channels from the HDHomeRun tuner to disk without re-encoding,
minimizing CPU overhead on low-power host devices.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app import jobs, media_probe, transcoding
from app.async_utils import drain_stderr_tail, run_in_background, terminate_process
from app.config import RECORDINGS_DIR, effective_settings, resolve_timezone
from app.dvr.builtin import poster_lookup
from app.dvr.media import captions_live, captions_static
from app.integrations import hdhomerun_client
from app.integrations.thesportsdb import extract_matchup_teams
from app.storage import db
from app.subprocess_streaming import STDERR_TAIL_BYTES

logger = logging.getLogger(__name__)

CAPTION_EXTRACTION_JOB_ID = "caption_extraction"

_FFMPEG_TERMINATE_TIMEOUT_SECONDS = 5
_MIN_RECORDING_BYTES = 10 * 1024  # at least 10KB to consider non-empty
_FILENAME_SAFE_RE = re.compile(r"[^\w]+")


async def _backfill_poster(
    recording_id: str,
    title: str,
    episode_title: str | None,
    season_number: int | None,
    episode_number: int | None,
    category: str | None,
) -> None:
    """Best-effort: look up `title` across TheSportsDB and TMDb and store its poster as this
    recording's image_url, but only if nothing else has set one in the
    meantime (a guide-sourced image_url always wins over this fallback)."""
    try:
        poster_url = await poster_lookup.find_poster_for_program(
            title=title,
            episode_title=episode_title,
            season_number=season_number,
            episode_number=episode_number,
            category=category,
        )
        if not poster_url:
            return

        current = await asyncio.to_thread(db.get_recording, recording_id)
        if current is None or current.get("image_url"):
            return

        await asyncio.to_thread(db.update_recording, recording_id, image_url=poster_url)
    except Exception:
        logger.debug("Poster backfill failed for recording [%s]", recording_id, exc_info=True)


def sanitize_filename(name: str) -> str:
    """Strip or replace characters that are invalid or problematic in filenames."""
    cleaned = _FILENAME_SAFE_RE.sub("_", name.strip()).strip("._")
    return cleaned or "recording"


@dataclass
class ActiveCapture:
    recording_id: str
    scheduled_id: str | None
    rule_id: str | None
    channel_number: str
    channel_name: str
    title: str
    episode_title: str | None
    season_number: int | None
    episode_number: int | None
    start_ts: float
    end_ts: float
    file_path: Path
    image_url: str | None
    process: asyncio.subprocess.Process
    synopsis: str | None = None
    original_air_date: str | None = None
    category: str | None = None
    drain_task: asyncio.Task[None] | None = None
    is_temporary: bool = False
    capture_quality: str | None = None
    viewer_session_ids: set[str] = field(default_factory=set)
    stderr_tail: bytearray = field(default_factory=bytearray)
    stderr_drain_done: asyncio.Event = field(default_factory=asyncio.Event)


class CapturePipeline:
    """Manages active FFmpeg recording processes.

    One ActiveCapture (one writer ffmpeg, one growing file) exists per
    channel at a time. `_channel_index` lets callers find the capture already
    running on a channel_number, so a live-watch session or a scheduled
    recording can attach to it (see app.dvr.builtin.watch/engine) instead of
    starting a second tuner/ffmpeg for the same channel.
    """

    def __init__(self) -> None:
        self._active_captures: dict[str, ActiveCapture] = {}
        self._channel_index: dict[str, str] = {}  # channel_number -> recording_id
        self._lock = asyncio.Lock()
        # Per-channel locks serializing get_or_start_capture callers (watch.py's
        # viewer-tune-in path and engine.py's scheduled-recording path) so a
        # channel with nothing running yet can only ever be claimed by one of
        # them - otherwise both can observe "no active capture" across their
        # own await points and each spawn an independent ffmpeg/tuner grab.
        self._channel_locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _ensure_recordings_dir(self) -> Path:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        return RECORDINGS_DIR

    def generate_file_path(
        self, title: str, episode_title: str | None, start_ts: float, recording_id: str, tz: ZoneInfo
    ) -> Path:
        recordings_dir = self._ensure_recordings_dir()
        parts = [sanitize_filename(title)[:50]]
        if episode_title:
            extra = "_".join(extract_matchup_teams(episode_title))
            parts.append(sanitize_filename(extra)[:60])
        air_date = datetime.fromtimestamp(start_ts, tz).strftime("%Y-%m-%d")
        filename = f"{'_'.join(parts)}_{air_date}_{recording_id[:8]}.ts"
        return recordings_dir / filename

    async def start_capture(
        self,
        recording_id: str,
        channel_number: str,
        channel_name: str,
        title: str,
        start_ts: float,
        end_ts: float,
        settings: dict[str, Any],
        scheduled_id: str | None = None,
        rule_id: str | None = None,
        episode_title: str | None = None,
        season_number: int | None = None,
        episode_number: int | None = None,
        synopsis: str | None = None,
        original_air_date: str | None = None,
        category: str | None = None,
        image_url: str | None = None,
        is_temporary: bool = False,
        quality: str | None = None,
    ) -> ActiveCapture | None:
        """Launch an FFmpeg stream-copy process writing to RECORDINGS_DIR.

        `quality`, when it names a tier in transcoding.TUNER_TRANSCODE_PROFILES
        and the tuner reports EXTEND-class hardware (see
        hdhomerun_client.probe_tuner_transcode_support), sources this capture
        from the tuner's own hardware-transcoded output instead of its raw
        stream - the capture ffmpeg still only stream-copies (the video is
        already encoded on the tuner's side), but re-encodes audio to AAC
        stereo since the tuner's own `?transcode=` audio handling is
        undocumented and this app already depends on that normalization for
        browser playback. Callers are responsible for falling back to a plain
        call (quality=None) if the resulting capture never produces data.
        """
        if not hdhomerun_client.is_tuner_configured(settings):
            logger.error("Cannot start capture: tuner is not configured")
            return None

        profile = transcoding.TUNER_TRANSCODE_PROFILES.get(quality or "")
        using_tuner_transcode = profile is not None and await hdhomerun_client.probe_tuner_transcode_support(
            settings
        )
        if using_tuner_transcode:
            assert profile is not None
            raw_url = hdhomerun_client.tuner_transcode_url(settings, channel_number, profile)
        else:
            raw_url = hdhomerun_client.raw_stream_url(settings, channel_number)
        app_settings = await asyncio.to_thread(effective_settings)
        file_path = self.generate_file_path(
            title, episode_title, start_ts, recording_id, resolve_timezone(app_settings.get("timezone", "UTC"))
        )

        codec_args = ["-c:v", "copy", "-c:a", "aac", "-ac", "2"] if using_tuner_transcode else ["-c", "copy"]
        argv = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            transcoding.resolve_loglevel(settings),
            "-reconnect",
            "1",
            "-reconnect_at_eof",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
            "-i",
            raw_url,
            *codec_args,
            "-map",
            "0",
            "-flush_packets",
            "1",
            "-f",
            "mpegts",
            "-y",
            str(file_path),
        ]

        logger.info(
            "Starting recording capture [%s] for '%s' on ch %s: %s -> %s",
            recording_id,
            title,
            channel_number,
            raw_url,
            file_path,
        )

        try:
            process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as exc:
            logger.error("Failed to launch ffmpeg for recording %s: %s", recording_id, exc)
            return None

        stderr_tail = bytearray()
        stderr_drain_done = asyncio.Event()
        drain_task = None
        if process.stderr is not None:
            drain_task = asyncio.create_task(
                drain_stderr_tail(process.stderr, stderr_tail, stderr_drain_done, tail_bytes=STDERR_TAIL_BYTES)
            )
        else:
            stderr_drain_done.set()

        capture = ActiveCapture(
            recording_id=recording_id,
            scheduled_id=scheduled_id,
            rule_id=rule_id,
            channel_number=channel_number,
            channel_name=channel_name,
            title=title,
            episode_title=episode_title,
            season_number=season_number,
            episode_number=episode_number,
            synopsis=synopsis,
            original_air_date=original_air_date,
            category=category,
            start_ts=start_ts,
            end_ts=end_ts,
            file_path=file_path,
            image_url=image_url,
            process=process,
            drain_task=drain_task,
            is_temporary=is_temporary,
            capture_quality=quality if using_tuner_transcode else None,
            stderr_tail=stderr_tail,
            stderr_drain_done=stderr_drain_done,
        )

        async with self._lock:
            self._active_captures[recording_id] = capture
            self._channel_index[channel_number] = recording_id

        # Record in database as in-progress
        rec_row = {
            "id": recording_id,
            "scheduled_recording_id": scheduled_id,
            "title": title,
            "episode_title": episode_title,
            "season_number": season_number,
            "episode_number": episode_number,
            "synopsis": synopsis,
            "channel_id": channel_number,
            "channel_name_snapshot": channel_name,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "original_air_date": original_air_date,
            "category": category,
            "file_path": str(file_path),
            "file_size_bytes": 0,
            "duration_seconds": None,
            "status": "recording",
            "image_url": image_url,
            "has_captions": 0,
            "is_temporary": 1 if is_temporary else 0,
        }
        await asyncio.to_thread(db.create_recording, rec_row)
        if scheduled_id:
            await asyncio.to_thread(
                db.update_recording,
                recording_id,
                status="recording",
            )
            # Update scheduled recording status
            await asyncio.to_thread(db.mark_scheduled_recording_in_progress, scheduled_id, recording_id)

        captions_live.ensure_live_captions(
            recording_id,
            file_path,
            lambda: self.is_capture_active(recording_id),
            capture_start_ts=start_ts,
        )

        return capture

    async def retune_to_raw(self, recording_id: str, settings: dict[str, Any]) -> bool:
        """Swap a running capture's writer from a tuner-hardware-transcoded
        source back to the tuner's raw stream, in place: same recording_id,
        same growing file (appended to, not truncated) - so callers
        (watch.promote_watch) don't need to change anything the player/DB
        already knows this capture by. No-op (returns False, capture left
        exactly as it was) if there's no active capture for recording_id or
        it isn't currently on a tuner-transcode profile.

        The old writer is fully terminated before the new one is spawned
        (rather than overlapping them) so the two processes never race to
        write the same file region - at the cost of a brief gap with no
        new data captured, which is an acceptable one-time cost for a
        user-initiated promote action.

        Returns False if the new writer couldn't be started - in that case
        the old one is already gone, so the capture's writer is gone too;
        callers should treat this capture as broken rather than promotable.
        """
        async with self._lock:
            capture = self._active_captures.get(recording_id)
        if capture is None or not capture.capture_quality:
            return False

        old_process = capture.process
        old_drain_task = capture.drain_task
        await terminate_process(old_process, timeout=_FFMPEG_TERMINATE_TIMEOUT_SECONDS)
        if old_drain_task is not None and not old_drain_task.done():
            old_drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await old_drain_task

        raw_url = hdhomerun_client.raw_stream_url(settings, capture.channel_number)
        argv = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            transcoding.resolve_loglevel(settings),
            "-reconnect",
            "1",
            "-reconnect_at_eof",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_delay_max",
            "5",
            "-i",
            raw_url,
            "-c",
            "copy",
            "-map",
            "0",
            "-flush_packets",
            "1",
            "-f",
            "mpegts",
            "pipe:1",
        ]

        logger.info(
            "Retuning capture [%s] from tuner-transcode profile '%s' back to raw: %s -> %s",
            recording_id,
            capture.capture_quality,
            raw_url,
            capture.file_path,
        )

        try:
            dest = await asyncio.to_thread(open, capture.file_path, "ab")
        except OSError as exc:
            logger.error("Cannot retune capture [%s] to raw: could not open %s for append: %s",
                         recording_id, capture.file_path, exc)
            return False
        try:
            new_process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=dest,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as exc:
            logger.error("Failed to launch raw-retune ffmpeg for capture %s: %s", recording_id, exc)
            return False
        finally:
            dest.close()

        new_stderr_tail = bytearray()
        new_stderr_drain_done = asyncio.Event()
        new_drain_task = None
        if new_process.stderr is not None:
            new_drain_task = asyncio.create_task(
                drain_stderr_tail(
                    new_process.stderr, new_stderr_tail, new_stderr_drain_done, tail_bytes=STDERR_TAIL_BYTES
                )
            )
        else:
            new_stderr_drain_done.set()

        async with self._lock:
            capture.process = new_process
            capture.drain_task = new_drain_task
            capture.stderr_tail = new_stderr_tail
            capture.stderr_drain_done = new_stderr_drain_done
            capture.capture_quality = None
        return True

    async def stop_capture(self, recording_id: str) -> dict[str, Any] | None:
        """Gracefully terminate FFmpeg capture, finalize database record and return stats."""
        async with self._lock:
            capture = self._active_captures.pop(recording_id, None)
            if capture is not None and self._channel_index.get(capture.channel_number) == recording_id:
                del self._channel_index[capture.channel_number]

        if capture is None:
            return None

        captions_live.stop_live_captions(recording_id)

        await terminate_process(capture.process, timeout=_FFMPEG_TERMINATE_TIMEOUT_SECONDS)

        if capture.drain_task and not capture.drain_task.done():
            capture.drain_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await capture.drain_task

        # Check final file stats
        now = time.time()
        file_size = 0
        if capture.file_path.exists():
            file_size = capture.file_path.stat().st_size

        duration = max(0.0, now - capture.start_ts)
        is_success = file_size >= _MIN_RECORDING_BYTES
        final_status = "completed" if is_success else "failed"

        # Media probe extraction for completed recordings
        video_codec = None
        video_width = None
        video_height = None
        audio_codec = None
        audio_channels = None
        has_captions = 0
        media_info_str = None

        if is_success and capture.file_path.exists():
            try:
                probe_info = await media_probe.probe(str(capture.file_path))
                if probe_info:
                    if probe_info.get("duration_seconds"):
                        duration = probe_info["duration_seconds"]
                    if probe_info.get("has_captions"):
                        has_captions = 1
                    video = probe_info.get("video") or {}
                    video_codec = video.get("codec")
                    video_width = video.get("width")
                    video_height = video.get("height")
                    audio_list = probe_info.get("audio") or []
                    if audio_list:
                        primary_audio = audio_list[0]
                        audio_codec = primary_audio.get("codec")
                        audio_channels = primary_audio.get("channels")
                    media_info_str = json.dumps(probe_info)
            except Exception as exc:
                logger.debug("Could not probe completed recording %s: %s", recording_id, exc)

        logger.info(
            "Finalized capture [%s] for '%s' (status=%s, size=%d bytes, duration=%.1fs)",
            recording_id,
            capture.title,
            final_status,
            file_size,
            duration,
        )

        # Update SQLite recordings table
        await asyncio.to_thread(
            db.update_recording,
            recording_id,
            end_ts=now,
            file_size_bytes=file_size,
            duration_seconds=duration,
            status=final_status,
            has_captions=has_captions,
            video_codec=video_codec,
            video_width=video_width,
            video_height=video_height,
            audio_codec=audio_codec,
            audio_channels=audio_channels,
            media_info=media_info_str,
        )

        if capture.scheduled_id:
            await asyncio.to_thread(db.update_scheduled_recording_status, capture.scheduled_id, final_status)

        if final_status == "completed" and not capture.image_url:
            run_in_background(
                _backfill_poster(
                    recording_id,
                    capture.title,
                    capture.episode_title,
                    capture.season_number,
                    capture.episode_number,
                    capture.category,
                )
            )

        if is_success and has_captions:
            jobs.run_tracked_in_background(
                CAPTION_EXTRACTION_JOB_ID,
                captions_static.generate_captions_vtt(str(capture.file_path), recording_id),
            )

        return {
            "recording_id": recording_id,
            "status": final_status,
            "file_size_bytes": file_size,
            "duration_seconds": duration,
            "file_path": str(capture.file_path),
            "rule_id": capture.rule_id,
            "title": capture.title,
        }

    async def get_active_capture(self, recording_id: str) -> ActiveCapture | None:
        async with self._lock:
            return self._active_captures.get(recording_id)

    async def get_active_capture_by_channel(self, channel_number: str) -> ActiveCapture | None:
        async with self._lock:
            recording_id = self._channel_index.get(channel_number)
            if recording_id is None:
                return None
            return self._active_captures.get(recording_id)

    async def get_or_start_capture(
        self,
        channel_number: str,
        start_fn: Callable[[], Awaitable[ActiveCapture | None]],
    ) -> tuple[ActiveCapture | None, bool]:
        """Atomically get the capture already running on channel_number, or
        run start_fn() to create one if none exists yet. Serializes every
        caller for a given channel behind one lock so at most one of them
        ever calls start_fn() - closing the race where a viewer tuning in and
        a scheduled recording starting at the same moment each independently
        see "nothing running" and spawn a second tuner/ffmpeg for the same
        channel. Returns (capture, created) - created is True only if
        start_fn() actually ran and produced a capture."""
        async with self._channel_locks[channel_number]:
            existing = await self.get_active_capture_by_channel(channel_number)
            if existing is not None:
                return existing, False
            capture = await start_fn()
            return capture, capture is not None

    def is_capture_active(self, recording_id: str | None) -> bool:
        """Lock-free check for the tail-follow pump's hot loop: is this
        capture's writer still running? (A dict lookup is atomic under the
        GIL, so no lock is needed for a single membership check.) `None`
        (a capture that was never resolved to a recording id) is simply
        never active."""
        return recording_id is not None and recording_id in self._active_captures

    async def wait_for_data(
        self,
        recording_id: str,
        min_bytes: int,
        timeout_seconds: float,
        poll_seconds: float = 0.2,
    ) -> bool:
        """Block until recording_id's capture has written at least min_bytes,
        or return False if it disappears, its writer process exits, or
        timeout_seconds elapses first. Used to confirm a capture actually
        works right after starting it - e.g. watch.py falling back to a raw
        capture when a tuner-hardware-transcode attempt never produces data."""
        deadline = time.monotonic() + timeout_seconds
        while True:
            capture = self._active_captures.get(recording_id)
            if capture is None:
                return False
            try:
                if capture.file_path.stat().st_size >= min_bytes:
                    return True
            except OSError:
                pass
            if capture.process is not None and capture.process.returncode is not None:
                return False
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(poll_seconds)

    async def add_viewer(self, recording_id: str, session_id: str) -> bool:
        """Register a live viewer against an active capture. Returns False if
        the capture no longer exists (caller should treat this like a miss)."""
        async with self._lock:
            capture = self._active_captures.get(recording_id)
            if capture is None:
                return False
            capture.viewer_session_ids.add(session_id)
            return True

    async def remove_viewer(self, recording_id: str, session_id: str) -> int:
        """Unregister a live viewer. Returns the remaining viewer count (0 if
        the capture no longer exists or had no viewers to begin with)."""
        async with self._lock:
            capture = self._active_captures.get(recording_id)
            if capture is None:
                return 0
            capture.viewer_session_ids.discard(session_id)
            return len(capture.viewer_session_ids)

    async def update_active_capture(self, recording_id: str, **fields: Any) -> bool:
        """Patch fields (e.g. end_ts, rule_id, title) on a running capture's in-memory
        state, so a later stop_capture() finalizes it with the updated values instead
        of what it was started with. Used when promoting a live-watch auto-capture
        (see app.dvr.builtin.watch) to a real recording."""
        async with self._lock:
            capture = self._active_captures.get(recording_id)
            if capture is None:
                return False
            for key, value in fields.items():
                setattr(capture, key, value)
            return True

    async def list_active_captures(self) -> list[ActiveCapture]:
        async with self._lock:
            return list(self._active_captures.values())


capture_pipeline = CapturePipeline()
