from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.dvr.builtin.tuner_allocator import TunerAllocator


@pytest.mark.asyncio
async def test_tuner_allocator_reports_zero_when_unconfigured():
    allocator = TunerAllocator()
    count = await allocator.get_tuner_count({})
    assert count == 0
    avail = await allocator.is_tuner_available({})
    assert avail is False


@pytest.mark.asyncio
async def test_tuner_allocator_reports_available_when_free(monkeypatch):
    allocator = TunerAllocator()
    settings = {"tuner_host": "192.168.1.100", "tuner_port": 80}

    from app.integrations import hdhomerun_client

    monkeypatch.setattr(hdhomerun_client, "fetch_discover", AsyncMock(return_value={"TunerCount": 2}))
    monkeypatch.setattr(
        hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(return_value=[{"in_use": False}, {"in_use": False}]),
    )

    assert await allocator.is_tuner_available(settings) is True
    assert await allocator.acquire_tuner("rec1", "4.1", settings) is True
    assert "rec1" in allocator.active_recording_ids()


@pytest.mark.asyncio
async def test_tuner_allocator_blocks_when_full(monkeypatch):
    allocator = TunerAllocator()
    settings = {"tuner_host": "192.168.1.100", "tuner_port": 80}

    from app.integrations import hdhomerun_client

    monkeypatch.setattr(hdhomerun_client, "fetch_discover", AsyncMock(return_value={"TunerCount": 2}))
    monkeypatch.setattr(
        hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(return_value=[{"in_use": False}, {"in_use": False}]),
    )

    assert await allocator.acquire_tuner("rec1", "4.1", settings) is True
    assert await allocator.acquire_tuner("rec2", "5.1", settings) is True
    # Capacity is 2; 3rd allocation should fail
    assert await allocator.is_tuner_available(settings) is False
    assert await allocator.acquire_tuner("rec3", "7.1", settings) is False

    # Release one
    await allocator.release_tuner("rec1")
    assert await allocator.is_tuner_available(settings) is True
    assert await allocator.acquire_tuner("rec3", "7.1", settings) is True


@pytest.mark.asyncio
async def test_tuner_allocator_respects_hardware_in_use(monkeypatch):
    allocator = TunerAllocator()
    settings = {"tuner_host": "192.168.1.100", "tuner_port": 80}

    from app.integrations import hdhomerun_client

    monkeypatch.setattr(hdhomerun_client, "fetch_discover", AsyncMock(return_value={"TunerCount": 2}))
    # Both hardware tuners are busy from other devices on LAN
    monkeypatch.setattr(
        hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(return_value=[{"in_use": True}, {"in_use": True}]),
    )

    assert await allocator.is_tuner_available(settings) is False
    assert await allocator.acquire_tuner("rec1", "4.1", settings) is False


@pytest.mark.asyncio
async def test_tuner_allocator_shares_one_slot_across_tokens_on_same_channel(monkeypatch):
    """A second token attaching to a channel that's already captured (e.g. a
    live-watch session joining a channel someone else is already recording)
    must not consume a second tuner slot."""
    allocator = TunerAllocator()
    settings = {"tuner_host": "192.168.1.100", "tuner_port": 80}

    from app.integrations import hdhomerun_client

    monkeypatch.setattr(hdhomerun_client, "fetch_discover", AsyncMock(return_value={"TunerCount": 2}))
    monkeypatch.setattr(
        hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(return_value=[{"in_use": False}, {"in_use": False}]),
    )

    assert await allocator.acquire_tuner("rec1", "4.1", settings) is True
    assert await allocator.acquire_tuner("viewer1", "4.1", settings) is True
    assert await allocator.channel_ref_count("4.1") == 2

    # Only one channel is occupied, so a second distinct channel can still
    # acquire the other tuner.
    assert await allocator.acquire_tuner("rec2", "5.1", settings) is True
    assert await allocator.is_tuner_available(settings) is False

    # Releasing the first token doesn't free the channel while another token
    # (the live viewer) is still attached.
    freed = await allocator.release_tuner("rec1")
    assert freed is False
    assert await allocator.channel_ref_count("4.1") == 1

    freed = await allocator.release_tuner("viewer1")
    assert freed is True
    assert await allocator.channel_ref_count("4.1") == 0


@pytest.mark.asyncio
async def test_tuner_allocator_release_channel_clears_all_tokens(monkeypatch):
    allocator = TunerAllocator()
    settings = {"tuner_host": "192.168.1.100", "tuner_port": 80}

    from app.integrations import hdhomerun_client

    monkeypatch.setattr(hdhomerun_client, "fetch_discover", AsyncMock(return_value={"TunerCount": 2}))
    monkeypatch.setattr(
        hdhomerun_client,
        "fetch_tuner_status",
        AsyncMock(return_value=[{"in_use": False}, {"in_use": False}]),
    )

    await allocator.acquire_tuner("rec1", "4.1", settings)
    await allocator.acquire_tuner("viewer1", "4.1", settings)
    await allocator.release_channel("4.1")

    assert await allocator.channel_ref_count("4.1") == 0
    assert "rec1" not in allocator.active_recording_ids()
    assert "viewer1" not in allocator.active_recording_ids()
