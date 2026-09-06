"""Parser for comskip/EDL commercial-cutlist sidecar files.

v1 scope: the classic EDL cutlist text format only - one entry per line,
whitespace-separated ``start_seconds end_seconds [type]``, where a missing
``type`` defaults to ``0`` (comskip's "commercial break" convention).
Comskip's alternate chapter ``.txt`` format is out of scope for now.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_edl_file(path: Path) -> list[dict[str, float]]:
    """Parse a comskip/EDL cutlist file into commercial-break segments.

    Returns ``[]`` if the file is missing or unreadable. Individual
    malformed lines are logged and skipped rather than aborting the whole
    parse. Only ``type == 0`` (commercial) entries with ``end > start`` are
    returned, sorted by ``start_seconds``.
    """
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []

    segments: list[dict[str, float]] = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if len(parts) < 2:
            logger.debug("Skipping malformed EDL line in %s: %r", path, line)
            continue

        try:
            start_seconds = float(parts[0])
            end_seconds = float(parts[1])
            entry_type = int(float(parts[2])) if len(parts) >= 3 else 0
        except ValueError:
            logger.debug("Skipping malformed EDL line in %s: %r", path, line)
            continue

        if entry_type != 0 or end_seconds <= start_seconds:
            continue

        segments.append({"start_seconds": start_seconds, "end_seconds": end_seconds})

    segments.sort(key=lambda seg: seg["start_seconds"])
    return segments
