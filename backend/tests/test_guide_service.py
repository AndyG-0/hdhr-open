from __future__ import annotations

import time
from unittest.mock import AsyncMock

from app.guide import service as guide_service
from app.storage import db
from app.storage.db import save_network_integration


def _configure_tuner(tmp_db):
    save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"tuner_host": "hdhomerun.local", "tuner_port": 80})


LINEUP = [{"channel_number": "4.1", "name": "WNBC", "is_hd": True, "is_drm": False, "stream_url": "http://x/4.1"}]


def _guide(start: float, end: float, title: str = "Some Show", episode_number: str | None = "1.2") -> list[dict]:
    return [
        {
            "channel_number": "4.1",
            "channel_name": "WNBC",
            "airings": [
                {
                    "series_id": "SH123",
                    "title": title,
                    "episode_title": "Pilot",
                    "episode_number": episode_number,
                    "synopsis": "A show begins.",
                    "start": start,
                    "end": end,
                    "original_airdate": "2020-01-01",
                    "image_url": "http://example.com/i.jpg",
                    "channel_number": "4.1",
                }
            ],
        }
    ]


async def test_refresh_noops_when_tuner_not_configured(tmp_db):
    await guide_service.refresh_hdhomerun_guide()

    assert db.list_channels(True) == []
    assert db.get_guide_provider_state(guide_service.SOURCE_PROVIDER) is None


async def test_refresh_creates_channel_and_guide_rows(tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    now = time.time()
    monkeypatch.setattr(guide_service.hdhomerun_client, "fetch_lineup", AsyncMock(return_value=LINEUP))
    monkeypatch.setattr(
        guide_service.hdhomerun_client, "fetch_full_guide", AsyncMock(return_value=_guide(now, now + 1800))
    )

    await guide_service.refresh_hdhomerun_guide()

    channel = db.get_channel_by_number("4.1")
    assert channel is not None
    rows = db.list_guide_programs([channel["id"]], now - 10, now + 3600)
    assert len(rows) == 1
    assert rows[0]["title"] == "Some Show"
    assert rows[0]["season_number"] == 1
    assert rows[0]["episode_number"] == 2
    state = db.get_guide_provider_state(guide_service.SOURCE_PROVIDER)
    assert state is not None and state["last_refreshed_at"]


async def test_refresh_purges_stale_programs(tmp_db, monkeypatch):
    # The first fetch schedules "Old Show" in a future slot; the second
    # fetch no longer mentions that slot at all (rescheduled away upstream)
    # and instead has "New Show" in a different slot. Since upsert alone
    # only replaces matching (channel_id, start_ts) rows, cleaning up the
    # orphaned "Old Show" slot requires the delete-then-upsert purge.
    _configure_tuner(tmp_db)
    now = time.time()
    monkeypatch.setattr(guide_service.hdhomerun_client, "fetch_lineup", AsyncMock(return_value=LINEUP))
    monkeypatch.setattr(
        guide_service.hdhomerun_client,
        "fetch_full_guide",
        AsyncMock(return_value=_guide(now + 7200, now + 9000, title="Old Show")),
    )
    await guide_service.refresh_hdhomerun_guide()

    monkeypatch.setattr(
        guide_service.hdhomerun_client,
        "fetch_full_guide",
        AsyncMock(return_value=_guide(now + 10800, now + 12600, title="New Show")),
    )
    await guide_service.refresh_hdhomerun_guide()

    channel = db.get_channel_by_number("4.1")
    rows = db.list_guide_programs([channel["id"]], now - 10, now + 20000)
    titles = {row["title"] for row in rows}
    assert titles == {"New Show"}


async def test_refresh_preserves_channel_favorite_across_runs(tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    now = time.time()
    monkeypatch.setattr(guide_service.hdhomerun_client, "fetch_lineup", AsyncMock(return_value=LINEUP))
    monkeypatch.setattr(
        guide_service.hdhomerun_client, "fetch_full_guide", AsyncMock(return_value=_guide(now, now + 1800))
    )
    await guide_service.refresh_hdhomerun_guide()
    channel = db.get_channel_by_number("4.1")
    db.update_channel(channel["id"], is_favorite=1)

    await guide_service.refresh_hdhomerun_guide()

    channel = db.get_channel_by_number("4.1")
    assert channel["is_favorite"] == 1


async def test_refresh_leaves_existing_data_when_guide_fetch_fails(tmp_db, monkeypatch):
    _configure_tuner(tmp_db)
    now = time.time()
    monkeypatch.setattr(guide_service.hdhomerun_client, "fetch_lineup", AsyncMock(return_value=LINEUP))
    monkeypatch.setattr(
        guide_service.hdhomerun_client, "fetch_full_guide", AsyncMock(return_value=_guide(now, now + 1800))
    )
    await guide_service.refresh_hdhomerun_guide()
    state_before = db.get_guide_provider_state(guide_service.SOURCE_PROVIDER)

    monkeypatch.setattr(guide_service.hdhomerun_client, "fetch_full_guide", AsyncMock(return_value=None))
    await guide_service.refresh_hdhomerun_guide()

    channel = db.get_channel_by_number("4.1")
    rows = db.list_guide_programs([channel["id"]], now - 10, now + 3600)
    assert len(rows) == 1
    assert db.get_guide_provider_state(guide_service.SOURCE_PROVIDER) == state_before
