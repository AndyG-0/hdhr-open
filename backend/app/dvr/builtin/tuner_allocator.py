"""Tuner allocation and concurrency management for the builtin DVR engine.

Ensures that recording captures do not exceed available hardware tuner units
on the HDHomeRun device and avoids double-booking.

Allocation is keyed by *channel*, not by caller: any number of tokens (a
scheduled recording's recording_id, a live-watch session's session_id) can be
attached to the same channel_number without consuming more than one tuner
slot, since they all end up reading the same underlying capture (see
app.dvr.builtin.capture/watch). Only the first token on a channel actually
needs a free hardware tuner - every subsequent one just joins the existing
allocation.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.integrations import hdhomerun_client

logger = logging.getLogger(__name__)

_DEFAULT_TUNER_COUNT = 2


class TunerAllocator:
    """Tracks active tuner usage across builtin recordings and live hardware status."""

    def __init__(self) -> None:
        self._channel_owners: dict[str, set[str]] = {}  # channel_number -> {token, ...}
        self._token_channel: dict[str, str] = {}  # token -> channel_number (reverse index)
        self._lock = asyncio.Lock()

    async def get_tuner_count(self, settings: dict[str, Any]) -> int:
        """Query total physical tuners on the HDHomeRun device."""
        if not hdhomerun_client.is_tuner_configured(settings):
            return 0
        try:
            discover = await hdhomerun_client.fetch_discover(settings)
            count = discover.get("TunerCount")
            if count is not None and isinstance(count, int) and count > 0:
                return count
        except Exception:
            logger.debug("Could not fetch discover.json for tuner count", exc_info=True)
        return _DEFAULT_TUNER_COUNT

    async def get_hardware_in_use_count(self, settings: dict[str, Any]) -> int:
        """Query currently active hardware tuner units on the device."""
        if not hdhomerun_client.is_tuner_configured(settings):
            return 0
        try:
            status = await hdhomerun_client.fetch_tuner_status(settings)
            return sum(1 for tuner in status if tuner.get("in_use"))
        except Exception:
            logger.debug("Could not fetch tuner status.json", exc_info=True)
            return 0

    async def is_tuner_available(self, settings: dict[str, Any], channel_number: str | None = None) -> bool:
        """Check if a tuner unit is free for a new recording.

        Attaching to a channel that already has an active capture never needs
        a free tuner - it joins the existing allocation instead of consuming
        another one.
        """
        if channel_number is not None:
            async with self._lock:
                if channel_number in self._channel_owners:
                    return True

        total_tuners = await self.get_tuner_count(settings)
        if total_tuners <= 0:
            return False

        async with self._lock:
            # Check internal active allocations (one slot per distinct channel)
            if len(self._channel_owners) >= total_tuners:
                return False

        # Check hardware-reported in-use count
        hw_in_use = await self.get_hardware_in_use_count(settings)
        async with self._lock:
            effective_in_use = max(hw_in_use, len(self._channel_owners))
            return effective_in_use < total_tuners

    async def acquire_tuner(self, token: str, channel_number: str, settings: dict[str, Any]) -> bool:
        """Attempt to reserve a tuner slot for channel_number under token.

        If channel_number is already owned by another token, this always
        succeeds and simply attaches token to it - no new tuner is consumed.
        Returns True if allocated/attached.
        """
        async with self._lock:
            if channel_number in self._channel_owners:
                self._channel_owners[channel_number].add(token)
                self._token_channel[token] = channel_number
                logger.info(
                    "Attached token %s to existing capture on channel %s (attached tokens: %d)",
                    token,
                    channel_number,
                    len(self._channel_owners[channel_number]),
                )
                return True

        if not await self.is_tuner_available(settings, channel_number):
            return False

        async with self._lock:
            # Another coroutine may have raced us and claimed this channel
            # between the availability check above and now.
            owners = self._channel_owners.setdefault(channel_number, set())
            owners.add(token)
            self._token_channel[token] = channel_number
            logger.info(
                "Allocated tuner for channel %s (token %s, total active channels: %d)",
                channel_number,
                token,
                len(self._channel_owners),
            )
            return True

    async def release_tuner(self, token: str) -> bool:
        """Detach token from whatever channel it was on.

        Returns True if this was the last token on that channel (the tuner
        slot is now actually free), False if other tokens remain attached or
        the token wasn't found.
        """
        async with self._lock:
            channel = self._token_channel.pop(token, None)
            if channel is None:
                return False
            owners = self._channel_owners.get(channel)
            if owners is None:
                return False
            owners.discard(token)
            if not owners:
                del self._channel_owners[channel]
                logger.info("Released last token for channel %s (token %s); tuner now free", channel, token)
                return True
            logger.info(
                "Released token %s for channel %s (remaining attached tokens: %d)", token, channel, len(owners)
            )
            return False

    async def release_channel(self, channel_number: str) -> None:
        """Force-release every token attached to channel_number at once.

        Used for forced teardown (e.g. a capture hitting its safety-cap
        end_ts) where multiple tokens - a scheduled recording plus any number
        of live viewers - may be sharing it and all need releasing together,
        regardless of per-token bookkeeping.
        """
        async with self._lock:
            tokens = self._channel_owners.pop(channel_number, None)
            if not tokens:
                return
            for token in tokens:
                self._token_channel.pop(token, None)
            logger.info("Force-released channel %s (%d attached tokens)", channel_number, len(tokens))

    async def channel_ref_count(self, channel_number: str) -> int:
        async with self._lock:
            return len(self._channel_owners.get(channel_number, ()))

    def active_recording_ids(self) -> set[str]:
        """Every token currently holding a tuner allocation (scheduled
        recording ids and/or live-watch session ids)."""
        return set(self._token_channel.keys())


tuner_allocator = TunerAllocator()
