"""HDHomeRun HTTP client for the HDHomeRun plugin.

Two independent, unauthenticated local-network devices are involved: the
tuner itself (channel lineup, per-tuner signal status) and, optionally, a
separate HDHomeRun DVR recording-engine service elsewhere on the LAN
(scheduled/in-progress recordings). Neither requires credentials. An
optional third connection — SSH to the DVR host, to disambiguate which
client(s) are actually streaming through its RECORD engine — does take
credentials, encrypted at rest like every other secret setting.

Program-guide data comes from SiliconDust's cloud API
(api.hdhomerun.com/api/guide.php), keyed by a `DeviceAuth` token from the
tuner's own /discover.json — requires an active HDHomeRun DVR subscription.
`fetch_full_guide` treats any failure (no subscription, network error,
unexpected shape) as "unavailable" rather than raising, so callers can
degrade gracefully. XMLTV guide fetching/parsing lives in `app.guide.xmltv`,
not here.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import socket
import struct
import time
import zlib
from typing import Any

import asyncssh
import httpx

from app.storage.cache import cache

logger = logging.getLogger(__name__)

HDHOMERUN_TYPE_GETSET_REQ = 0x0004
HDHOMERUN_TYPE_GETSET_RPY = 0x0005
HDHOMERUN_TAG_GETSET_NAME = 0x03
HDHOMERUN_TAG_GETSET_VALUE = 0x04
HDHOMERUN_TAG_ERROR_MESSAGE = 0x05
HDHOMERUN_CONTROL_PORT = 65001

_GUIDE_URL = "https://api.hdhomerun.com/api/guide.php"
_RULES_URL = "https://api.hdhomerun.com/api/recording_rules"
_DISCOVER_CACHE_TTL_SECONDS = 3600
_FULL_GUIDE_CACHE_TTL_SECONDS = 3600
# guide.php's "Duration" param caps a single request at 24 hours of programs
# per channel (default is 4 if omitted). Getting more days requires repeated
# requests, walking "Start" forward by _FULL_GUIDE_PAGE_HOURS each time. These
# bound how far/long we'll page — 14 days matches SiliconDust's documented
# DVR-subscriber ceiling; free accounts simply stop returning new data around
# 3 days and the loop below ends naturally at that point.
_FULL_GUIDE_PAGE_HOURS = 24
_FULL_GUIDE_MAX_DAYS = 14
_FULL_GUIDE_MAX_REQUESTS = 20


class HDHomeRunError(Exception):
    """Raised when an HDHomeRun device can't be reached or rejects a request."""


def is_tuner_configured(settings: dict[str, Any]) -> bool:
    return bool(settings.get("tuner_host"))


def is_dvr_configured(settings: dict[str, Any]) -> bool:
    return bool(settings.get("dvr_host"))


def is_dvr_ssh_configured(settings: dict[str, Any]) -> bool:
    return bool(settings.get("dvr_ssh_enabled") and settings.get("dvr_ssh_host") and settings.get("dvr_ssh_username"))


def _normalize_host(host: str) -> str:
    # Users will naturally paste a full URL (with scheme and/or a trailing
    # slash) into a "host" field — strip that down to a bare hostname/IP
    # rather than building a malformed URL out of it.
    host = host.strip()
    for prefix in ("http://", "https://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    host = host.rstrip("/")
    if ":" in host and not host.startswith("["):
        host = host.split(":", 1)[0]
    return host


def _tuner_base_url(settings: dict[str, Any]) -> str:
    return f"http://{_normalize_host(settings['tuner_host'])}:{settings.get('tuner_port', 80)}"


def raw_stream_url(settings: dict[str, Any], channel_number: str) -> str:
    """The tuner's own raw MPEG-TS stream URL for a channel (port 5004,
    fixed by the HDHomeRun HTTP API — distinct from the discovery/JSON API
    port configured via `tuner_port`)."""
    host = _normalize_host(settings["tuner_host"])
    return f"http://{host}:5004/auto/v{channel_number}"


def _dvr_base_url(settings: dict[str, Any]) -> str:
    host = settings.get("dvr_host") or settings.get("tuner_host", "")
    port = settings.get("dvr_port") or 59090
    return f"http://{_normalize_host(host)}:{port}"


def resolve_recording_url(settings: dict[str, Any], url: str) -> str:
    """A recording/tuner-relative `play_url` resolved to a fully-qualified URL.

    Shared by every route that needs to actually reach the bytes a
    recording entry's `play_url` points at (streaming, probing, caption/
    thumbnail generation) — previously duplicated inline in
    app/api/hdhomerun.py's /recording-stream route.
    """
    if url.startswith("/"):
        if url.startswith("/auto/v"):
            tuner_host = _normalize_host(settings.get("tuner_host", ""))
            return f"http://{tuner_host}:5004{url}"
        dvr_host = _normalize_host(settings.get("dvr_host") or settings.get("tuner_host", ""))
        port = settings.get("dvr_port") or 59090
        return f"http://{dvr_host}:{port}{url}"
    if not url.startswith("http"):
        dvr_host = _normalize_host(settings.get("dvr_host") or settings.get("tuner_host", ""))
        port = settings.get("dvr_port") or 59090
        return f"http://{dvr_host}:{port}/{url}"
    return url


async def _get_json(url: str) -> Any:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        raise HDHomeRunError(f"Could not reach {url}: {exc}") from exc
    if response.status_code >= 400:
        raise HDHomeRunError(f"Request to {url} failed (HTTP {response.status_code}).")
    try:
        return response.json()
    except ValueError as exc:
        # e.g. the wrong port is configured and it's returning something
        # other than JSON (a video stream, an HTML error page, etc).
        raise HDHomeRunError(f"Unexpected (non-JSON) response from {url}: {exc}") from exc


async def fetch_discover(settings: dict[str, Any]) -> dict[str, Any]:
    return await _get_json(f"{_tuner_base_url(settings)}/discover.json")


def _channel_dict(entry: dict[str, Any]) -> dict[str, Any]:
    tags = entry.get("Tags", "")
    return {
        "channel_number": entry.get("GuideNumber", ""),
        "name": entry.get("GuideName", ""),
        "is_hd": bool(entry.get("HD")) or "hd" in tags,
        "is_drm": bool(entry.get("DRM")) or "drm" in tags,
        "stream_url": entry.get("URL", ""),
    }


async def fetch_lineup(settings: dict[str, Any]) -> list[dict[str, Any]]:
    data = await _get_json(f"{_tuner_base_url(settings)}/lineup.json")
    return [_channel_dict(entry) for entry in data or []]


def _tuner_status_dict(entry: dict[str, Any], index: int) -> dict[str, Any]:
    # Field names vary by firmware/model and aren't fully documented — read
    # everything defensively so an unexpected shape degrades to missing
    # fields rather than raising.
    target_ip = entry.get("TargetIP")
    if target_ip == "none":
        target_ip = None
    return {
        "index": index,
        "resource": entry.get("Resource") or f"tuner{index}",
        "in_use": bool(entry.get("VctNumber") or target_ip),
        "channel_number": entry.get("VctNumber"),
        "channel_name": entry.get("VctName"),
        "target_ip": target_ip,
        "signal_strength_percent": entry.get("SignalStrengthPercent"),
        "signal_quality_percent": entry.get("SignalQualityPercent"),
        "symbol_quality_percent": entry.get("SymbolQualityPercent"),
        "network_rate_bps": entry.get("NetworkRate") or entry.get("NetworkRateBps"),
    }


async def fetch_tuner_status(settings: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        data = await _get_json(f"{_tuner_base_url(settings)}/status.json")
    except HDHomeRunError:
        logger.debug("Could not fetch tuner status.json", exc_info=True)
        return []
    if not isinstance(data, list):
        return []
    return [_tuner_status_dict(entry, index) for index, entry in enumerate(data)]


def _encode_tlv(tag: int, value: bytes) -> bytes:
    length = len(value)
    if length < 0x80:
        len_bytes = bytes([length])
    else:
        len_bytes = bytes([0x80 | (length & 0x7F), length >> 7])
    return bytes([tag]) + len_bytes + value


def _parse_tlv_dict(payload: bytes) -> dict[int, bytes]:
    result: dict[int, bytes] = {}
    idx = 0
    while idx < len(payload):
        tag = payload[idx]
        idx += 1
        if idx >= len(payload):
            break
        length = payload[idx]
        idx += 1
        if length & 0x80:
            if idx >= len(payload):
                break
            length = (length & 0x7F) | (payload[idx] << 7)
            idx += 1
        if idx + length > len(payload):
            break
        value = payload[idx : idx + length]
        idx += length
        result[tag] = value
    return result


def _build_getset_req_packet(name: str, value: str | None = None) -> bytes:
    payload = _encode_tlv(HDHOMERUN_TAG_GETSET_NAME, name.encode("ascii") + b"\x00")
    if value is not None:
        payload += _encode_tlv(HDHOMERUN_TAG_GETSET_VALUE, value.encode("ascii") + b"\x00")
    header = struct.pack(">HH", HDHOMERUN_TYPE_GETSET_REQ, len(payload))
    packet_without_crc = header + payload
    crc = zlib.crc32(packet_without_crc) & 0xFFFFFFFF
    return packet_without_crc + struct.pack("<I", crc)


async def set_tuner_variable(
    settings: dict[str, Any], variable: str, value: str, timeout: float = 3.0
) -> bool:
    """Send a native GETSET command to the HDHomeRun hardware over TCP port 65001,
    with fallback to hdhomerun_config CLI if available."""
    if not is_tuner_configured(settings):
        return False
    host = _normalize_host(settings["tuner_host"])
    port = HDHOMERUN_CONTROL_PORT
    req_pkt = _build_getset_req_packet(variable, value)

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        try:
            writer.write(req_pkt)
            await writer.drain()
            header = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
            pkt_type, payload_len = struct.unpack(">HH", header)
            payload = await asyncio.wait_for(reader.readexactly(payload_len), timeout=timeout)
            _crc_bytes = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
            if pkt_type == HDHOMERUN_TYPE_GETSET_RPY:
                tlvs = _parse_tlv_dict(payload)
                if HDHOMERUN_TAG_ERROR_MESSAGE in tlvs:
                    err_msg = tlvs[HDHOMERUN_TAG_ERROR_MESSAGE].decode("ascii", errors="replace").rstrip("\x00")
                    logger.warning("HDHomeRun command (%s = %s) rejected by %s: %s", variable, value, host, err_msg)
                    return False
                val_msg = tlvs.get(HDHOMERUN_TAG_GETSET_VALUE, b"").decode("ascii", errors="replace").rstrip("\x00")
                logger.info("Successfully set HDHomeRun variable %s = %s on %s (reply: %s)", variable, value, host, val_msg)
                return True
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
    except Exception as exc:
        logger.debug("Native control command (%s = %s) to %s:%s failed: %s", variable, value, host, port, exc)

    # Fallback to hdhomerun_config CLI if installed
    try:
        proc = await asyncio.create_subprocess_exec(
            "hdhomerun_config",
            host,
            "set",
            variable,
            value,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode == 0:
            logger.info("Successfully set HDHomeRun variable %s = %s via hdhomerun_config on %s", variable, value, host)
            return True
    except (FileNotFoundError, OSError, TimeoutError):
        pass

    return False


async def release_hardware_tuner(settings: dict[str, Any], tuner_index: int) -> bool:
    """Clear lock, channel, and target on a physical HDHomeRun tuner unit, releasing any lock or stream."""
    # 1. Force-release any lockkey held by a client/DVR engine
    lock_ok = await set_tuner_variable(settings, f"/tuner{tuner_index}/lockkey", "force")
    # 2. Stop network streaming target
    target_ok = await set_tuner_variable(settings, f"/tuner{tuner_index}/target", "none")
    # 3. Clear physical channel frequency
    channel_ok = await set_tuner_variable(settings, f"/tuner{tuner_index}/channel", "none")
    # 4. Clear virtual channel number
    vchannel_ok = await set_tuner_variable(settings, f"/tuner{tuner_index}/vchannel", "none")
    return lock_ok or target_ok or channel_ok or vchannel_ok


_DNS_CACHE: dict[str, tuple[str | None, float]] = {}
_DNS_CACHE_TTL = 300.0  # 5 minutes


async def resolve_hostname(ip: str | None) -> str | None:
    """Asynchronously resolve IP address to hostname with a 1-second timeout and caching."""
    if not ip or ip in ("127.0.0.1", "::1", "none"):
        return None

    clean_ip = ip
    if "://" in clean_ip:
        clean_ip = clean_ip.split("://", 1)[1]
    if ":" in clean_ip and not clean_ip.startswith("["):
        clean_ip = clean_ip.split(":", 1)[0]
    clean_ip = clean_ip.strip("[]")

    now = time.time()
    cached = _DNS_CACHE.get(clean_ip)
    if cached and now < cached[1]:
        return cached[0]

    def _lookup() -> str | None:
        try:
            name, _, _ = socket.gethostbyaddr(clean_ip)
            return name
        except (socket.herror, socket.gaierror, OSError):
            return None

    try:
        hostname = await asyncio.wait_for(asyncio.to_thread(_lookup), timeout=1.0)
    except Exception:
        hostname = None

    _DNS_CACHE[clean_ip] = (hostname, now + _DNS_CACHE_TTL)
    return hostname


def _guide_entry_dict(entry: dict[str, Any], channel_number: str = "") -> dict[str, Any]:
    filters = entry.get("Filter")
    if isinstance(filters, list):
        category = ", ".join(str(f) for f in filters if f)
    else:
        category = entry.get("Category")

    audio_props = entry.get("AudioProperties") or entry.get("Audio")
    if isinstance(audio_props, list):
        audio_str = ", ".join(str(a) for a in audio_props if a)
    elif audio_props:
        audio_str = str(audio_props)
    else:
        audio_str = None

    is_new = bool(entry.get("First") or entry.get("New") or entry.get("IsNew") or entry.get("OriginalAirdate") == entry.get("Airdate"))
    has_cc = bool(entry.get("CC") or entry.get("ClosedCaption") or True)

    return {
        "series_id": entry.get("SeriesID"),
        "title": entry.get("Title", ""),
        "episode_title": entry.get("EpisodeTitle"),
        "episode_number": entry.get("EpisodeNumber"),
        "synopsis": entry.get("Synopsis"),
        "start": entry.get("StartTime"),
        "end": entry.get("EndTime"),
        "original_airdate": entry.get("OriginalAirdate"),
        "image_url": entry.get("ImageURL"),
        "channel_number": channel_number or entry.get("ChannelNumber", ""),
        "category": category,
        "audio": audio_str,
        "is_new": is_new,
        "has_cc": has_cc,
    }


async def fetch_full_guide(settings: dict[str, Any], widget_id: str) -> list[dict[str, Any]] | None:
    guide_cache_key = f"hdhomerun_full_guide:{widget_id}"
    cached = cache.get(guide_cache_key)
    if cached is not None:
        return cached

    discover_cache_key = f"hdhomerun_discover:{widget_id}"
    discover = cache.get(discover_cache_key)
    if discover is None:
        try:
            discover = await fetch_discover(settings)
        except HDHomeRunError:
            logger.debug("Could not fetch discover.json for cloud guide lookup", exc_info=True)
            return None
        cache.set(discover_cache_key, discover, _DISCOVER_CACHE_TTL_SECONDS)

    device_auth = discover.get("DeviceAuth")
    if not device_auth:
        return None

    channels_by_number: dict[str, dict[str, Any]] = {}
    seen_starts_by_channel: dict[str, set[Any]] = {}
    any_page_succeeded = False
    # Look back 4 hours so airings currently in progress are included in the response.
    page_start = int(time.time()) - 4 * 3600
    num_pages = _FULL_GUIDE_MAX_DAYS * 24 // _FULL_GUIDE_PAGE_HOURS

    async with httpx.AsyncClient(timeout=10) as client:
        for _ in range(min(num_pages, _FULL_GUIDE_MAX_REQUESTS)):
            params: dict[str, Any] = {
                "DeviceAuth": device_auth,
                "Start": page_start,
                "Duration": _FULL_GUIDE_PAGE_HOURS,
            }
            try:
                response = await client.get(_GUIDE_URL, params=params)
                if response.status_code >= 400:
                    break
                data = response.json()
            except (httpx.HTTPError, ValueError):
                logger.debug("Could not fetch cloud program guide", exc_info=True)
                break

            if not isinstance(data, list):
                break
            any_page_succeeded = True
            if not data:
                break  # No more data — past the free/subscribed guide window.

            got_new_entries = False
            for channel in data:
                ch_num = channel.get("GuideNumber", "")
                ch_name = channel.get("GuideName", "")
                guide_entries = channel.get("Guide") or []
                entry = channels_by_number.setdefault(
                    ch_num, {"channel_number": ch_num, "channel_name": ch_name, "airings": []}
                )
                seen_starts = seen_starts_by_channel.setdefault(ch_num, set())

                for e in guide_entries:
                    if not isinstance(e, dict):
                        continue
                    start = e.get("StartTime")
                    if start in seen_starts:
                        continue
                    seen_starts.add(start)
                    entry["airings"].append(_guide_entry_dict(e, ch_num))
                    got_new_entries = True

            if not got_new_entries:
                break  # No channel had anything for this page — reached the end.

            page_start += _FULL_GUIDE_PAGE_HOURS * 3600

    if not any_page_succeeded:
        return None

    result = list(channels_by_number.values())
    cache.set(guide_cache_key, result, _FULL_GUIDE_CACHE_TTL_SECONDS)
    return result


async def test_tuner_connection(settings: dict[str, Any]) -> str:
    discover = await fetch_discover(settings)
    return discover.get("FriendlyName", "HDHomeRun")


async def test_dvr_connection(settings: dict[str, Any]) -> str:
    discover = await _get_json(f"{_dvr_base_url(settings)}/discover.json")
    return discover.get("FriendlyName", "HDHomeRun DVR")


async def fetch_dvr_info(settings: dict[str, Any]) -> dict[str, Any]:
    discover = await _get_json(f"{_dvr_base_url(settings)}/discover.json")
    return {
        "friendly_name": discover.get("FriendlyName", "HDHomeRun DVR"),
        "version": discover.get("Version"),
        "free_space_bytes": discover.get("FreeSpace"),
    }


async def _dvr_ssh_connect(settings: dict[str, Any]) -> asyncssh.SSHClientConnection:
    key = settings.get("dvr_ssh_key") or None
    return await asyncssh.connect(
        _normalize_host(settings["dvr_ssh_host"]),
        port=int(settings.get("dvr_ssh_port") or 22),
        username=settings.get("dvr_ssh_username") or None,
        password=settings.get("dvr_ssh_password") or None,
        client_keys=[asyncssh.import_private_key(key)] if key else None,
        # A LAN-local DVR box the user has already identified by address —
        # same trust posture as the tuner/DVR HTTP connections above, which
        # have no cert verification either.
        known_hosts=None,
    )


async def test_dvr_ssh_connection(settings: dict[str, Any]) -> str:
    if not is_dvr_ssh_configured(settings):
        raise HDHomeRunError("DVR SSH monitoring is not configured")
    try:
        conn = await asyncio.wait_for(_dvr_ssh_connect(settings), timeout=5.0)
    except (OSError, asyncssh.Error, ValueError, TimeoutError) as exc:
        raise HDHomeRunError(f"Could not SSH to {settings.get('dvr_ssh_host')}: {exc}") from exc
    try:
        await asyncio.wait_for(conn.run("true", check=True), timeout=5.0)
    except (asyncssh.Error, TimeoutError) as exc:
        raise HDHomeRunError(f"SSH connected but command failed: {exc}") from exc
    finally:
        conn.close()
        with contextlib.suppress(Exception):
            await conn.wait_closed()
    return f"Connected to {settings.get('dvr_ssh_host')} via SSH"


# Socket-inspection commands to try, in order, against the DVR host's
# streaming port — ss (modern Linux), lsof (BSD/macOS-style NAS OSes), then
# netstat (oldest/most portable fallback). Each is tried only if the
# previous one wasn't found or errored, not merely because it reported zero
# current connections (that's a legitimate "nobody's watching" result).
_SSH_SOCKET_COMMANDS = (
    "ss -tnp '( sport = :{port} )'",
    "lsof -n -P -i :{port}",
    "netstat -tnp | grep :{port}",
)
_SSH_CLIENTS_CACHE_TTL_SECONDS = 10  # live connection state, not the stable
# DNS-hostname data resolve_hostname() caches for 300s — a longer TTL here
# would show stale viewers after they've disconnected.


def _parse_ssh_socket_clients(output: str, port: int) -> list[str]:
    """Extract distinct peer IPs from ss/lsof/netstat output for connections
    on `port`, tolerating the three tools' differing column layouts by just
    reading off the two IP:PORT pairs present on each matching line."""
    port_str = str(port)
    ips: list[str] = []
    for line in output.splitlines():
        pairs = re.findall(r"(\d{1,3}(?:\.\d{1,3}){3}):(\d+)", line)
        if len(pairs) != 2:
            continue
        (ip_a, port_a), (ip_b, port_b) = pairs
        peer_ip = ip_b if port_a == port_str else ip_a if port_b == port_str else None
        if peer_ip and peer_ip not in ips:
            ips.append(peer_ip)
    return ips


async def fetch_dvr_ssh_clients(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """SSH into the DVR host and inspect who's connected to its RECORD-engine
    streaming port, to attribute an otherwise-anonymous `dvr_proxy` tuner
    client to the actual device(s) watching through it. Never raises —
    every failure (unconfigured, unreachable, no usable inspection command)
    degrades to an empty list so callers can fall back to the plain
    "HDHomeRun RECORD (<ip>)" display.
    """
    if not is_dvr_ssh_configured(settings):
        return []

    port = settings.get("dvr_port") or 50000
    cache_key = f"hdhomerun_dvr_ssh_clients:{settings.get('dvr_ssh_host')}:{port}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    result: list[dict[str, Any]] = []
    try:
        conn = await asyncio.wait_for(_dvr_ssh_connect(settings), timeout=2.0)
    except (OSError, asyncssh.Error, ValueError, TimeoutError):
        logger.debug("Could not SSH to DVR host for client inspection", exc_info=True)
        cache.set(cache_key, result, _SSH_CLIENTS_CACHE_TTL_SECONDS)
        return result

    try:
        ips: list[str] = []
        for command_template in _SSH_SOCKET_COMMANDS:
            try:
                proc = await asyncio.wait_for(
                    conn.run(command_template.format(port=port), check=False), timeout=2.0
                )
            except (asyncssh.Error, TimeoutError):
                continue
            if proc.exit_status != 0:
                continue
            ips = _parse_ssh_socket_clients(proc.stdout or "", port)
            break
    finally:
        conn.close()
        with contextlib.suppress(Exception):
            await conn.wait_closed()

    for ip in ips:
        result.append({"ip": ip, "hostname": await resolve_hostname(ip)})

    cache.set(cache_key, result, _SSH_CLIENTS_CACHE_TTL_SECONDS)
    return result


def _recording_dict(entry: dict[str, Any]) -> dict[str, Any]:
    play_url = (
        entry.get("PlayURL")
        or entry.get("PlayUrl")
        or entry.get("CmdURL")
        or entry.get("CmdUrl")
        or entry.get("URL")
        or entry.get("Url")
        or entry.get("RecordURL")
        or entry.get("RecordUrl")
    )
    rec_id = entry.get("RecordingID") or entry.get("ProgramID") or entry.get("ID")
    if not play_url and rec_id:
        play_url = f"/recorded/{rec_id}"
    elif not play_url and entry.get("Filename"):
        play_url = entry.get("Filename")

    start = entry.get("StartTime") or entry.get("RecordStartTime")
    record_end = entry.get("RecordEndTime") or entry.get("EndTime")

    return {
        "recording_id": rec_id,
        "series_id": entry.get("SeriesID"),
        "title": entry.get("Title", ""),
        "episode_title": entry.get("EpisodeTitle"),
        "episode_number": entry.get("EpisodeNumber"),
        "synopsis": entry.get("Synopsis"),
        "channel_number": entry.get("ChannelNumber"),
        "channel_name": entry.get("ChannelAffiliate") or entry.get("ChannelName"),
        "start": start,
        "record_end": record_end,
        # Cheap/approximate — the exact duration for a completed recording
        # comes from ffprobe instead (see app/media_probe.py), which the
        # player prefers once it's fetched. This is what's shown before
        # that request lands, and the only duration available at all for a
        # still-recording (record_end in the future) entry.
        "duration_seconds": (record_end - start) if (start is not None and record_end is not None) else None,
        "play_url": play_url,
        "image_url": entry.get("ImageURL"),
        "category": entry.get("Category"),
        "category_type": _classify_hdhomerun_category(entry),
        # Marks this as a real DVR file entry (as opposed to the
        # synthesized "currently airing, no file yet" placeholders
        # HDHomeRunPlugin.get_detail() adds from recording rules) — only
        # these are seekable, since seeking needs an actual file/URL on the
        # DVR to -ss into, not a bare live tuner stream.
        "is_dvr_file": True,
    }


def _classify_hdhomerun_category(entry: dict[str, Any]) -> str:
    from app.dvr.builtin.poster_lookup import classify_category

    return classify_category(
        title=entry.get("Title", ""),
        episode_title=entry.get("EpisodeTitle"),
        category=entry.get("Category"),
    )


async def fetch_dvr_recordings(settings: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        dvr_base = _dvr_base_url(settings)
        discover = await _get_json(f"{dvr_base}/discover.json")
        storage_url = discover.get("StorageURL")
        if not storage_url:
            return []
        if not storage_url.startswith("http"):
            storage_url = f"{dvr_base}/{storage_url.lstrip('/')}"
        data = await _get_json(storage_url)
    except HDHomeRunError:
        logger.debug("Could not fetch DVR recordings", exc_info=True)
        return []
    if not isinstance(data, list):
        return []

    episodes = []
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for entry in data:
                episodes_url = entry.get("EpisodesURL")
                if episodes_url:
                    if not episodes_url.startswith("http"):
                        episodes_url = f"{dvr_base}/{episodes_url.lstrip('/')}"
                    resp = await client.get(episodes_url)
                    if resp.status_code < 400:
                        episodes.extend(resp.json())
                else:
                    episodes.append(entry)
    except (httpx.HTTPError, ValueError):
        logger.debug("Could not fetch DVR episodes", exc_info=True)

    return [_recording_dict(entry) for entry in episodes]


async def fetch_dvr_recording_rules(settings: dict[str, Any]) -> list[dict[str, Any]]:
    if is_tuner_configured(settings):
        try:
            discover = await fetch_discover(settings)
            device_auth = discover.get("DeviceAuth")
            if device_auth:
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(_RULES_URL, params={"DeviceAuth": device_auth})
                if resp.status_code < 400 and resp.json() is not None:
                    res = resp.json()
                    if isinstance(res, list):
                        return res
        except Exception:
            logger.debug("Could not fetch cloud recording rules", exc_info=True)

    if is_dvr_configured(settings):
        try:
            data = await _get_json(f"{_dvr_base_url(settings)}/recording_rules.json")
            if isinstance(data, list):
                return data
        except HDHomeRunError:
            logger.debug("Could not fetch local DVR recording rules", exc_info=True)

    return []


async def trigger_dvr_sync(settings: dict[str, Any]) -> None:
    """Notify local DVR storage to recompute recording tasks after a rule change."""
    if not is_dvr_configured(settings):
        return
    try:
        discover = await _get_json(f"{_dvr_base_url(settings)}/discover.json")
        storage_url = discover.get("StorageURL")
        if storage_url:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.get(storage_url)
    except (HDHomeRunError, httpx.HTTPError):
        logger.debug("Could not send sync trigger to DVR StorageURL", exc_info=True)


def _rules_or_raise(rules: Any) -> list[dict[str, Any]]:
    """The recording_rules API always documents a JSON array as its success shape.

    A rejected request (e.g. no active HDHomeRun DVR subscription) still comes
    back as HTTP 200, but with an object/error body instead of a list — silently
    treating that as "zero rules" would report success for a rule that was never
    actually created, leaving nothing for the DVR engine to ever record.
    """
    if isinstance(rules, list):
        return rules
    message = None
    if isinstance(rules, dict):
        message = rules.get("error") or rules.get("Error") or rules.get("ErrorMessage")
    raise HDHomeRunError(message or f"HDHomeRun rejected the recording rule request: {rules!r}")


async def add_recording_rule(settings: dict[str, Any], rule_data: dict[str, Any]) -> list[dict[str, Any]]:
    if not is_tuner_configured(settings):
        raise HDHomeRunError("Tuner is not configured")

    discover = await fetch_discover(settings)
    device_auth = discover.get("DeviceAuth")
    if not device_auth:
        raise HDHomeRunError("No DeviceAuth token available from tuner discovery")

    post_data: dict[str, Any] = {
        "DeviceAuth": device_auth,
        "Cmd": "add",
    }
    series_id = rule_data.get("series_id")
    if series_id and series_id != "auto":
        post_data["SeriesID"] = series_id

    now_ts = int(time.time())
    dt = rule_data.get("date_time")
    if dt is not None:
        # If date_time is in the past (e.g. current show's start time when recording a live airing),
        # adjust to current timestamp so SiliconDust API records the active show instead of expiring
        # or picking a future episode.
        if dt < now_ts:
            dt = now_ts
        post_data["DateTimeOnly"] = dt

    if "channel" in rule_data and rule_data["channel"]:
        post_data["ChannelOnly"] = rule_data["channel"]
    if "recent_only" in rule_data and rule_data["recent_only"] is not None:
        post_data["RecentOnly"] = 1 if rule_data["recent_only"] else 0
    if "start_padding" in rule_data and rule_data["start_padding"] is not None:
        post_data["StartPadding"] = rule_data["start_padding"]
    if "end_padding" in rule_data and rule_data["end_padding"] is not None:
        post_data["EndPadding"] = rule_data["end_padding"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(_RULES_URL, data=post_data)
        if response.status_code >= 400:
            raise HDHomeRunError(f"Add recording rule failed (HTTP {response.status_code})")
        rules = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HDHomeRunError(f"Could not post recording rule: {exc}") from exc

    rules = _rules_or_raise(rules)
    await trigger_dvr_sync(settings)
    return rules


async def delete_recording_rule(settings: dict[str, Any], rule_id: str) -> list[dict[str, Any]]:
    if not is_tuner_configured(settings):
        raise HDHomeRunError("Tuner is not configured")

    discover = await fetch_discover(settings)
    device_auth = discover.get("DeviceAuth")
    if not device_auth:
        raise HDHomeRunError("No DeviceAuth token available from tuner discovery")

    post_data = {
        "DeviceAuth": device_auth,
        "Cmd": "delete",
        "RecordingRuleID": rule_id,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(_RULES_URL, data=post_data)
        if response.status_code >= 400:
            raise HDHomeRunError(f"Delete recording rule failed (HTTP {response.status_code})")
        rules = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HDHomeRunError(f"Could not delete recording rule: {exc}") from exc

    rules = _rules_or_raise(rules)
    await trigger_dvr_sync(settings)
    return rules
