"""Shared "is this a major over-the-air network" classification, used to
auto-resolve a broadcast-network name (from ESPN, or any other source) to a
canonical OTA token that can be matched against a channel's `affiliate`
column (see app.dvr.builtin.discovery and app.dvr.builtin.sports_autorecord).

HDHomeRun's lineup.json `Affiliate` field isn't a clean enum - format varies
by market/firmware - so this takes the leading alphabetic run of the field
(strips trailing digits/"-DT"/"HD" suffixes) and explicitly denylists cable
lookalikes rather than trying to allowlist every real-world variant.
"""

from __future__ import annotations

import re

MAJOR_NETWORKS = {"NBC", "CBS", "ABC", "FOX", "CW", "PBS"}
MAJOR_NETWORK_DENYLIST = {
    "FOXNEWS",
    "FOXBUSINESS",
    "FOXSPORTS",
    "FOXSPORTS1",
    "FOXSPORTS2",
    "FS1",
    "FS2",
    "NBCSN",
    "NBCSPORTS",
    "NBCUNIVERSO",
    "NBCNEWS",
    "ABCNEWS",
    "CWSEED",
    "PBSKIDS",
}


def normalize_major_network_token(value: str | None) -> str | None:
    """Returns the canonical OTA token (e.g. "CBS") if `value` names a major
    over-the-air network, else None. Matches both HDHomeRun's `affiliate`
    field and ESPN's free-text `broadcast_network` strings."""
    if not value:
        return None
    match = re.match(r"[A-Za-z]+", value.strip())
    if not match:
        return None
    token = match.group(0).upper()
    if token in MAJOR_NETWORK_DENYLIST:
        return None
    return token if token in MAJOR_NETWORKS else None


def is_major_network(affiliate: str | None) -> bool:
    return normalize_major_network_token(affiliate) is not None
