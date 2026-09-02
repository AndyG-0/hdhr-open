from __future__ import annotations

import time

import httpx
import pytest
import respx

from app.integrations import hdhomerun_client
from app.storage.cache import cache

TUNER_SETTINGS = {"tuner_host": "hdhr.local", "tuner_port": 80, "dvr_host": "", "dvr_port": 50000}
DVR_SETTINGS = {**TUNER_SETTINGS, "dvr_host": "dvr.local", "dvr_port": 50000}

DISCOVER_RESPONSE = {
    "FriendlyName": "HDHomeRun FLEX 4K",
    "ModelNumber": "HDFX-4K",
    "FirmwareVersion": "20260326",
    "DeviceID": "10AFFFFF",
    "DeviceAuth": "sometoken",
    "LineupURL": "http://hdhr.local/lineup.json",
    "TunerCount": 4,
}

LINEUP_RESPONSE = [
    {"GuideNumber": "4.1", "GuideName": "WCMH-DT", "HD": 1, "URL": "http://hdhr.local:5004/auto/v4.1"},
    {"GuideNumber": "7.1", "GuideName": "WHIO-DT", "Tags": "drm", "URL": "http://hdhr.local:5004/auto/v7.1"},
]


def test_is_tuner_configured_true_with_host():
    assert hdhomerun_client.is_tuner_configured(TUNER_SETTINGS)


def test_is_tuner_configured_false_without_host():
    assert not hdhomerun_client.is_tuner_configured({"tuner_host": ""})


def test_is_dvr_configured_true_with_host():
    assert hdhomerun_client.is_dvr_configured(DVR_SETTINGS)


def test_is_dvr_configured_false_without_host():
    assert not hdhomerun_client.is_dvr_configured(TUNER_SETTINGS)


@respx.mock
async def test_fetch_discover_returns_json():
    respx.get("http://hdhr.local:80/discover.json").mock(return_value=httpx.Response(200, json=DISCOVER_RESPONSE))

    result = await hdhomerun_client.fetch_discover(TUNER_SETTINGS)

    assert result["FriendlyName"] == "HDHomeRun FLEX 4K"


@respx.mock
async def test_fetch_discover_raises_on_error():
    respx.get("http://hdhr.local:80/discover.json").mock(return_value=httpx.Response(500))

    with pytest.raises(hdhomerun_client.HDHomeRunError):
        await hdhomerun_client.fetch_discover(TUNER_SETTINGS)


@respx.mock
async def test_fetch_discover_raises_hdhomerun_error_on_non_json_response():
    # e.g. tuner_port pointed at the streaming port instead of the JSON API
    # port — should degrade like any other reachability failure, not crash
    # with an unhandled ValueError.
    respx.get("http://hdhr.local:80/discover.json").mock(
        return_value=httpx.Response(200, content=b"\x00\x01\x02not json")
    )

    with pytest.raises(hdhomerun_client.HDHomeRunError):
        await hdhomerun_client.fetch_discover(TUNER_SETTINGS)


@respx.mock
async def test_fetch_discover_normalizes_host_with_scheme_and_trailing_slash():
    respx.get("http://hdhr.local:80/discover.json").mock(return_value=httpx.Response(200, json=DISCOVER_RESPONSE))

    result = await hdhomerun_client.fetch_discover({**TUNER_SETTINGS, "tuner_host": "http://hdhr.local/"})

    assert result["FriendlyName"] == "HDHomeRun FLEX 4K"


@respx.mock
async def test_fetch_lineup_maps_channels():
    respx.get("http://hdhr.local:80/lineup.json").mock(return_value=httpx.Response(200, json=LINEUP_RESPONSE))

    channels = await hdhomerun_client.fetch_lineup(TUNER_SETTINGS)

    assert channels[0] == {
        "channel_number": "4.1",
        "name": "WCMH-DT",
        "is_hd": True,
        "is_drm": False,
        "stream_url": "http://hdhr.local:5004/auto/v4.1",
    }
    assert channels[1]["is_drm"] is True
    assert channels[1]["is_hd"] is False


@respx.mock
async def test_fetch_tuner_status_maps_defensively_when_fields_missing():
    respx.get("http://hdhr.local:80/status.json").mock(return_value=httpx.Response(200, json=[{}]))

    statuses = await hdhomerun_client.fetch_tuner_status(TUNER_SETTINGS)

    assert statuses == [
        {
            "index": 0,
            "resource": "tuner0",
            "in_use": False,
            "channel_number": None,
            "channel_name": None,
            "target_ip": None,
            "signal_strength_percent": None,
            "signal_quality_percent": None,
            "symbol_quality_percent": None,
            "network_rate_bps": None,
        }
    ]


@respx.mock
async def test_fetch_tuner_status_returns_empty_list_on_error():
    respx.get("http://hdhr.local:80/status.json").mock(return_value=httpx.Response(500))

    statuses = await hdhomerun_client.fetch_tuner_status(TUNER_SETTINGS)

    assert statuses == []


@respx.mock
async def test_fetch_full_guide_paginates_across_multiple_days():
    cache.delete("hdhomerun_full_guide:w7")
    now = int(time.time())
    page1 = [
        {
            "GuideNumber": "4.1",
            "GuideName": "WCMH-DT",
            "Guide": [{"StartTime": now, "EndTime": now + 8 * 3600, "Title": "Show A"}],
        }
    ]
    page2 = [
        {
            "GuideNumber": "4.1",
            "GuideName": "WCMH-DT",
            "Guide": [{"StartTime": now + 24 * 3600, "EndTime": now + 25 * 3600, "Title": "Show B"}],
        }
    ]
    page3: list = []
    respx.get("http://hdhr.local:80/discover.json").mock(return_value=httpx.Response(200, json=DISCOVER_RESPONSE))
    guide_route = respx.get("https://api.hdhomerun.com/api/guide.php")
    guide_route.side_effect = [
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
        httpx.Response(200, json=page3),
    ]

    guide = await hdhomerun_client.fetch_full_guide(TUNER_SETTINGS, "w7")

    assert guide_route.call_count == 3
    assert len(guide) == 1
    titles = [a["title"] for a in guide[0]["airings"]]
    assert titles == ["Show A", "Show B"]
    first_params = guide_route.calls[0].request.url.params
    expected_start = now - 4 * 3600
    assert abs(int(first_params["Start"]) - expected_start) <= 2
    assert first_params["Duration"] == "24"
    second_params = guide_route.calls[1].request.url.params
    assert abs(int(second_params["Start"]) - (expected_start + 24 * 3600)) <= 2


@respx.mock
async def test_fetch_full_guide_stops_when_page_has_no_entries():
    cache.delete("hdhomerun_full_guide:w8")
    now = int(time.time())
    page1 = [
        {
            "GuideNumber": "4.1",
            "GuideName": "WCMH-DT",
            "Guide": [{"StartTime": now, "EndTime": now + 8 * 3600, "Title": "Show A"}],
        }
    ]
    # A channel entry with an empty Guide list — reached the free/subscribed
    # data ceiling but the response still lists the channel.
    page2 = [{"GuideNumber": "4.1", "GuideName": "WCMH-DT", "Guide": []}]
    respx.get("http://hdhr.local:80/discover.json").mock(return_value=httpx.Response(200, json=DISCOVER_RESPONSE))
    guide_route = respx.get("https://api.hdhomerun.com/api/guide.php")
    guide_route.side_effect = [httpx.Response(200, json=page1), httpx.Response(200, json=page2)]

    guide = await hdhomerun_client.fetch_full_guide(TUNER_SETTINGS, "w8")

    assert guide_route.call_count == 2
    assert len(guide[0]["airings"]) == 1


@respx.mock
async def test_fetch_full_guide_caches_result():
    cache.delete("hdhomerun_full_guide:w9")
    guide_route = respx.get("https://api.hdhomerun.com/api/guide.php").mock(return_value=httpx.Response(200, json=[]))
    respx.get("http://hdhr.local:80/discover.json").mock(return_value=httpx.Response(200, json=DISCOVER_RESPONSE))

    await hdhomerun_client.fetch_full_guide(TUNER_SETTINGS, "w9")
    await hdhomerun_client.fetch_full_guide(TUNER_SETTINGS, "w9")

    assert guide_route.call_count == 1


@respx.mock
async def test_fetch_full_guide_returns_none_on_total_failure():
    cache.delete("hdhomerun_full_guide:w10")
    respx.get("http://hdhr.local:80/discover.json").mock(return_value=httpx.Response(200, json=DISCOVER_RESPONSE))
    respx.get("https://api.hdhomerun.com/api/guide.php").mock(return_value=httpx.Response(403))

    guide = await hdhomerun_client.fetch_full_guide(TUNER_SETTINGS, "w10")

    assert guide is None


@respx.mock
async def test_test_tuner_connection_returns_friendly_name():
    respx.get("http://hdhr.local:80/discover.json").mock(return_value=httpx.Response(200, json=DISCOVER_RESPONSE))

    name = await hdhomerun_client.test_tuner_connection(TUNER_SETTINGS)

    assert name == "HDHomeRun FLEX 4K"


@respx.mock
async def test_test_tuner_connection_raises_on_error():
    respx.get("http://hdhr.local:80/discover.json").mock(return_value=httpx.Response(500))

    with pytest.raises(hdhomerun_client.HDHomeRunError):
        await hdhomerun_client.test_tuner_connection(TUNER_SETTINGS)


@respx.mock
async def test_test_dvr_connection_returns_friendly_name():
    respx.get("http://dvr.local:50000/discover.json").mock(
        return_value=httpx.Response(200, json={"FriendlyName": "HDHomeRun RECORD"})
    )

    name = await hdhomerun_client.test_dvr_connection(DVR_SETTINGS)

    assert name == "HDHomeRun RECORD"


@respx.mock
async def test_test_dvr_connection_raises_on_error():
    respx.get("http://dvr.local:50000/discover.json").mock(return_value=httpx.Response(500))

    with pytest.raises(hdhomerun_client.HDHomeRunError):
        await hdhomerun_client.test_dvr_connection(DVR_SETTINGS)


@respx.mock
async def test_fetch_dvr_recordings_degrades_to_empty_list_on_error():
    respx.get("http://dvr.local:50000/discover.json").mock(return_value=httpx.Response(500))

    recordings = await hdhomerun_client.fetch_dvr_recordings(DVR_SETTINGS)

    assert recordings == []


@respx.mock
async def test_fetch_dvr_recordings_maps_fields():
    respx.get("http://dvr.local:50000/discover.json").mock(
        return_value=httpx.Response(
            200, json={"FriendlyName": "HDHomeRun RECORD", "StorageURL": "http://dvr.local:50000/recorded_files.json"}
        )
    )
    respx.get("http://dvr.local:50000/recorded_files.json").mock(
        return_value=httpx.Response(200, json=[{"Title": "Local News", "ChannelAffiliate": "NBC"}])
    )

    recordings = await hdhomerun_client.fetch_dvr_recordings(DVR_SETTINGS)

    assert recordings[0]["title"] == "Local News"
    assert recordings[0]["channel_name"] == "NBC"


@respx.mock
async def test_fetch_dvr_recording_rules_degrades_to_empty_list_on_error():
    respx.get("http://dvr.local:50000/recording_rules.json").mock(return_value=httpx.Response(500))

    rules = await hdhomerun_client.fetch_dvr_recording_rules(DVR_SETTINGS)

    assert rules == []


def test_resolve_recording_url_with_dvr_settings():
    assert (
        hdhomerun_client.resolve_recording_url(DVR_SETTINGS, "/recorded/123")
        == "http://dvr.local:50000/recorded/123"
    )


def test_resolve_recording_url_falls_back_to_tuner_host_when_dvr_host_empty():
    assert (
        hdhomerun_client.resolve_recording_url(TUNER_SETTINGS, "/recorded/123")
        == "http://hdhr.local:50000/recorded/123"
    )


def test_resolve_recording_url_preserves_absolute_http_url():
    assert (
        hdhomerun_client.resolve_recording_url(TUNER_SETTINGS, "http://192.168.1.50:50000/recorded/123")
        == "http://192.168.1.50:50000/recorded/123"
    )


def test_resolve_recording_url_resolves_tuner_stream():
    assert (
        hdhomerun_client.resolve_recording_url(TUNER_SETTINGS, "/auto/v4.1")
        == "http://hdhr.local:5004/auto/v4.1"
    )


@respx.mock
async def test_fetch_dvr_recordings_handles_relative_storage_and_episodes_urls():
    respx.get("http://dvr.local:50000/discover.json").mock(
        return_value=httpx.Response(
            200, json={"FriendlyName": "HDHomeRun RECORD", "StorageURL": "/recorded_files.json"}
        )
    )
    respx.get("http://dvr.local:50000/recorded_files.json").mock(
        return_value=httpx.Response(200, json=[{"EpisodesURL": "/episodes.json?SeriesID=101"}])
    )
    respx.get("http://dvr.local:50000/episodes.json?SeriesID=101").mock(
        return_value=httpx.Response(200, json=[{"Title": "Series Episode 1", "PlayURL": "/recorded/101_1"}])
    )

    recordings = await hdhomerun_client.fetch_dvr_recordings(DVR_SETTINGS)

    assert len(recordings) == 1
    assert recordings[0]["title"] == "Series Episode 1"
    assert recordings[0]["play_url"] == "/recorded/101_1"


def test_build_getset_req_packet():
    packet = hdhomerun_client._build_getset_req_packet("/tuner0/target", "none")
    assert len(packet) > 8
    # Packet starts with big-endian type 0x0004
    assert packet[:2] == b"\x00\x04"


async def test_set_tuner_variable_requires_configured_tuner():
    ok = await hdhomerun_client.set_tuner_variable({"tuner_host": ""}, "/tuner0/target", "none")
    assert ok is False


async def test_set_tuner_variable_success_with_mock_socket(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    reader = AsyncMock()
    reader.readexactly = AsyncMock(side_effect=[
        b"\x00\x05\x00\x00",  # Header: TYPE_GETSET_RPY, payload_len=0
        b"",                  # Payload
        b"\x00\x00\x00\x00",  # CRC
    ])
    writer = MagicMock()
    writer.write = MagicMock()
    writer.drain = AsyncMock()
    writer.close = MagicMock()
    writer.wait_closed = AsyncMock()

    monkeypatch.setattr(asyncio, "open_connection", AsyncMock(return_value=(reader, writer)))

    ok = await hdhomerun_client.set_tuner_variable(TUNER_SETTINGS, "/tuner0/target", "none")
    assert ok is True


async def test_release_hardware_tuner_calls_channel_and_target(monkeypatch):
    from unittest.mock import AsyncMock
    mock_set = AsyncMock(return_value=True)
    monkeypatch.setattr(hdhomerun_client, "set_tuner_variable", mock_set)

    ok = await hdhomerun_client.release_hardware_tuner(TUNER_SETTINGS, 0)
    assert ok is True
    assert mock_set.call_count == 4


async def test_resolve_hostname_returns_none_for_empty():
    assert await hdhomerun_client.resolve_hostname(None) is None
    assert await hdhomerun_client.resolve_hostname("") is None
    assert await hdhomerun_client.resolve_hostname("127.0.0.1") is None


SSH_SETTINGS = {
    **DVR_SETTINGS,
    "dvr_ssh_enabled": True,
    "dvr_ssh_host": "dvr.local",
    "dvr_ssh_port": 22,
    "dvr_ssh_username": "root",
    "dvr_ssh_key": "",
    "dvr_ssh_password": "hunter2",
}


def test_is_dvr_ssh_configured():
    assert hdhomerun_client.is_dvr_ssh_configured(SSH_SETTINGS) is True
    assert hdhomerun_client.is_dvr_ssh_configured({**SSH_SETTINGS, "dvr_ssh_enabled": False}) is False
    assert hdhomerun_client.is_dvr_ssh_configured({**SSH_SETTINGS, "dvr_ssh_host": ""}) is False


async def test_fetch_dvr_ssh_clients_not_configured_skips_ssh(monkeypatch):
    from unittest.mock import AsyncMock

    connect_mock = AsyncMock()
    monkeypatch.setattr(hdhomerun_client.asyncssh, "connect", connect_mock)

    clients = await hdhomerun_client.fetch_dvr_ssh_clients(DVR_SETTINGS)
    assert clients == []
    connect_mock.assert_not_called()


async def test_fetch_dvr_ssh_clients_ss_format(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    ss_output = (
        "State  Recv-Q Send-Q Local Address:Port   Peer Address:Port  Process\n"
        "ESTAB  0      0      192.168.1.200:50000  192.168.1.50:54321 "
        'users:(("hdhomerun_record",pid=1234,fd=10))\n'
    )
    conn = AsyncMock()
    conn.run = AsyncMock(return_value=MagicMock(exit_status=0, stdout=ss_output))
    conn.close = MagicMock()
    conn.wait_closed = AsyncMock()
    monkeypatch.setattr(hdhomerun_client.asyncssh, "connect", AsyncMock(return_value=conn))
    monkeypatch.setattr(hdhomerun_client, "resolve_hostname", AsyncMock(return_value="roku.local"))

    clients = await hdhomerun_client.fetch_dvr_ssh_clients(SSH_SETTINGS)
    assert clients == [{"ip": "192.168.1.50", "hostname": "roku.local"}]
    assert conn.run.call_count == 1  # ss succeeded — no fallback to lsof/netstat
    cache.delete("hdhomerun_dvr_ssh_clients:dvr.local:50000")


async def test_fetch_dvr_ssh_clients_falls_back_to_lsof(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    lsof_output = (
        "COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\n"
        "hdhomerun 1234 root   10u  IPv4 123456      0t0  TCP "
        "192.168.1.200:50000->192.168.1.51:54322 (ESTABLISHED)\n"
    )
    conn = AsyncMock()
    conn.run = AsyncMock(
        side_effect=[
            MagicMock(exit_status=127, stdout=""),  # ss: command not found
            MagicMock(exit_status=0, stdout=lsof_output),
        ]
    )
    conn.close = MagicMock()
    conn.wait_closed = AsyncMock()
    monkeypatch.setattr(hdhomerun_client.asyncssh, "connect", AsyncMock(return_value=conn))
    monkeypatch.setattr(hdhomerun_client, "resolve_hostname", AsyncMock(return_value=None))

    clients = await hdhomerun_client.fetch_dvr_ssh_clients(SSH_SETTINGS)
    assert clients == [{"ip": "192.168.1.51", "hostname": None}]
    assert conn.run.call_count == 2
    cache.delete("hdhomerun_dvr_ssh_clients:dvr.local:50000")


async def test_fetch_dvr_ssh_clients_falls_back_to_netstat(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    netstat_output = "tcp  0  0  192.168.1.200:50000  192.168.1.52:54323  ESTABLISHED 1234/hdhomerun_record\n"
    conn = AsyncMock()
    conn.run = AsyncMock(
        side_effect=[
            MagicMock(exit_status=127, stdout=""),  # ss: not found
            MagicMock(exit_status=127, stdout=""),  # lsof: not found
            MagicMock(exit_status=0, stdout=netstat_output),
        ]
    )
    conn.close = MagicMock()
    conn.wait_closed = AsyncMock()
    monkeypatch.setattr(hdhomerun_client.asyncssh, "connect", AsyncMock(return_value=conn))
    monkeypatch.setattr(hdhomerun_client, "resolve_hostname", AsyncMock(return_value=None))

    clients = await hdhomerun_client.fetch_dvr_ssh_clients(SSH_SETTINGS)
    assert clients == [{"ip": "192.168.1.52", "hostname": None}]
    assert conn.run.call_count == 3
    cache.delete("hdhomerun_dvr_ssh_clients:dvr.local:50000")


async def test_fetch_dvr_ssh_clients_swallows_connection_error(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(hdhomerun_client.asyncssh, "connect", AsyncMock(side_effect=OSError("unreachable")))

    clients = await hdhomerun_client.fetch_dvr_ssh_clients(SSH_SETTINGS)
    assert clients == []
    cache.delete("hdhomerun_dvr_ssh_clients:dvr.local:50000")


async def test_test_dvr_ssh_connection_success(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    conn = AsyncMock()
    conn.run = AsyncMock(return_value=MagicMock(exit_status=0))
    conn.close = MagicMock()
    conn.wait_closed = AsyncMock()
    monkeypatch.setattr(hdhomerun_client.asyncssh, "connect", AsyncMock(return_value=conn))

    result = await hdhomerun_client.test_dvr_ssh_connection(SSH_SETTINGS)
    assert "dvr.local" in result


async def test_test_dvr_ssh_connection_requires_configuration():
    with pytest.raises(hdhomerun_client.HDHomeRunError):
        await hdhomerun_client.test_dvr_ssh_connection(DVR_SETTINGS)


async def test_test_dvr_ssh_connection_raises_on_unreachable_host(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(hdhomerun_client.asyncssh, "connect", AsyncMock(side_effect=OSError("no route to host")))

    with pytest.raises(hdhomerun_client.HDHomeRunError):
        await hdhomerun_client.test_dvr_ssh_connection(SSH_SETTINGS)


async def test_resolve_hostname_resolves_and_caches(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "gethostbyaddr", lambda ip: ("my-device.local", [], [ip]))

    hostname = await hdhomerun_client.resolve_hostname("192.168.1.99")
    assert hostname == "my-device.local"
    # Second call uses cache
    assert await hdhomerun_client.resolve_hostname("192.168.1.99") == "my-device.local"


