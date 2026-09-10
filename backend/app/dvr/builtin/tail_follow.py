"""Tail-follow reader for a growing MPEG-TS capture file.

An in-progress DVR capture (see app.dvr.builtin.capture) is a file that's
still being appended to by the writer ffmpeg. A plain `ffmpeg -i <path>`
input catches up to whatever's flushed to disk and then hits a real EOF and
exits - exactly like reading a normal completed file - so a live viewer
attached to an in-progress recording would stall the moment they caught up
to the writer instead of continuing to watch live.

This is deliberately NOT a shelled-out `tail -F <path>`: this backend runs on
macOS (see app/transcoding.py's VideoToolbox preset), and macOS's BSD `tail`
has no `-F`/follow-by-descriptor mode. A hand-rolled async pump gives the
same behavior (keep reading past EOF, tolerate the file being replaced)
without depending on GNU coreutils being installed.

MPEG-TS's fixed 188-byte packet framing means starting to read from any
*packet-aligned* offset in the file is exactly as safe as a live tuner
channel-change or a `recording-stream` seek elsewhere in this codebase - no
keyframe alignment is needed at this layer, only packet alignment; the
downstream decoder resyncs on the packet sync byte within whatever GOP it
lands in. Callers that compute a byte offset from a time estimate (see
`_estimate_byte_offset` in app/api/dvr.py) MUST round it down to a multiple
of 188 themselves - passing an arbitrary unaligned byte offset here will
desync every subsequent "packet" this function reads and corrupt the
downstream ffmpeg's parse.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

_READ_CHUNK_BYTES = 188 * 348  # ~64KB, a whole number of TS packets
_POLL_INTERVAL_SECONDS = 0.05
_MAX_EOF_POLLS_WITHOUT_GROWTH = 100  # ~5s of a genuinely stalled-but-alive source


async def pump_tail_follow(
    file_path: Path,
    writer: asyncio.StreamWriter,
    stop_event: asyncio.Event,
    is_source_alive: Callable[[], bool],
    start_offset_bytes: int | None = None,
) -> None:
    """Read file_path from start_offset_bytes (default: near the current end,
    i.e. the live edge) and write every chunk to `writer`, blocking past EOF
    and retrying instead of stopping - until stop_event fires, is_source_alive()
    goes false, or the peer closes `writer`.
    """
    try:
        fh = await asyncio.to_thread(open, file_path, "rb")
    except OSError as exc:
        logger.warning("tail-follow: could not open %s: %s", file_path, exc)
        return

    start_monotonic = time.monotonic()
    total_written = 0
    # Set right before whichever return actually fires below, then logged
    # once in the finally block - every exit path (including the implicit
    # one, the while condition going false because stop_event fired) needs
    # to show up here, since a peer that stops reading mid-stream (see the
    # BrokenPipeError case) is exactly the kind of thing that otherwise
    # leaves zero trace of why a downstream decoder went quiet.
    exit_reason = "stop_event set"
    try:
        size = await asyncio.to_thread(lambda: file_path.stat().st_size)
        offset = start_offset_bytes if start_offset_bytes is not None else size
        offset = max(0, min(offset, size))
        await asyncio.to_thread(fh.seek, offset)
        logger.info("tail-follow: starting %s from byte offset %d (size at start %d)", file_path, offset, size)

        eof_polls = 0
        while not stop_event.is_set():
            chunk = await asyncio.to_thread(fh.read, _READ_CHUNK_BYTES)
            if chunk:
                eof_polls = 0
                try:
                    writer.write(chunk)
                    await writer.drain()
                except (ConnectionResetError, BrokenPipeError) as exc:
                    exit_reason = f"peer closed its end of the pipe ({type(exc).__name__})"
                    return
                total_written += len(chunk)
                continue

            # Real EOF for now - the writer may still be appending.
            if not is_source_alive():
                exit_reason = "source no longer alive"
                return

            eof_polls += 1
            if eof_polls > _MAX_EOF_POLLS_WITHOUT_GROWTH:
                # The writer process is alive but nothing has been flushed in
                # a while (reconnecting to the tuner, hiccup, etc.) - keep
                # waiting rather than giving up; the viewer's player already
                # tolerates a brief live-TV stall.
                eof_polls = 0

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=_POLL_INTERVAL_SECONDS)
            except TimeoutError:
                pass
    finally:
        logger.info(
            "tail-follow: stopping (%s) after writing %d bytes over %.1fs from %s",
            exit_reason,
            total_written,
            time.monotonic() - start_monotonic,
            file_path,
        )
        with contextlib.suppress(Exception):
            await asyncio.to_thread(fh.close)
