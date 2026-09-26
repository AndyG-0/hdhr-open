from __future__ import annotations

import time
import uuid

from app.api.dvr_rules import _lookup_guide_title, _lookup_hdhomerun_series_id
from app.storage import db


def _seed_channel_with_airing(channel_number: str, title: str, series_id: str, start_offset: float = 1000) -> None:
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, channel_number, channel_number, True)
    now = time.time()
    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "hdhomerun_cloud",
                "external_program_id": series_id,
                "title": title,
                "start_ts": now + start_offset,
                "end_ts": now + start_offset + 1800,
            }
        ]
    )


def test_lookup_hdhomerun_series_id_matches_requested_channel(tmp_db):
    _seed_channel_with_airing("12.1", "The Tonight Show Starring Jimmy Fallon", "SH012345670000")

    result = _lookup_hdhomerun_series_id("12.1", None, "The Tonight Show Starring Jimmy Fallon")

    assert result == "SH012345670000"


def test_lookup_hdhomerun_series_id_does_not_widen_to_other_channels(tmp_db):
    # Same title airs on a different channel with a different (e.g.
    # market-specific) SeriesID. A rule locked to "12.1" must never resolve
    # to this one - doing so would create a rule that can never match a
    # real 12.1 airing and would silently never record anything.
    _seed_channel_with_airing("5.1", "The Tonight Show Starring Jimmy Fallon", "SH999999999999")

    result = _lookup_hdhomerun_series_id("12.1", None, "The Tonight Show Starring Jimmy Fallon")

    assert result is None


def test_lookup_guide_title_does_not_widen_to_other_channels(tmp_db):
    channel_id = uuid.uuid4().hex
    db.upsert_channel(channel_id, "5.1", "5.1", True)
    now = time.time()
    date_time = int(now + 1000)
    db.upsert_guide_programs(
        [
            {
                "channel_id": channel_id,
                "source_provider": "hdhomerun_cloud",
                "external_program_id": "EP1",
                "title": "Some Show",
                "start_ts": date_time,
                "end_ts": date_time + 1800,
            }
        ]
    )

    # channel "12.1" doesn't exist at all - must not fall back to matching
    # the airing on channel 5.1 at the same timestamp.
    result = _lookup_guide_title(None, "12.1", date_time)

    assert result == "Channel 12.1"
