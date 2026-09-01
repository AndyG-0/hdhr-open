from __future__ import annotations

import time
from unittest.mock import AsyncMock
from xml.etree import ElementTree

from app.guide import xmltv as guide_xmltv
from app.storage import db
from app.storage.db import save_network_integration


def _configure_xmltv(url: str = "http://example.com/guide.xml") -> None:
    save_network_integration("xmltv", "xmltv", "XMLTV", {"url": url})


def _root(xml: str) -> ElementTree.Element:
    return ElementTree.fromstring(xml)


def _xmltv_time(ts: float) -> str:
    return time.strftime("%Y%m%d%H%M%S +0000", time.gmtime(ts))


async def test_refresh_noops_when_unconfigured(tmp_db):
    await guide_xmltv.refresh_xmltv_guide()

    assert db.get_guide_provider_state(guide_xmltv.SOURCE_PROVIDER) is None


async def test_refresh_noops_when_no_tuner_channels(tmp_db, monkeypatch):
    _configure_xmltv()
    now = time.time()
    xml = f"""<tv>
        <channel id="4.1"><display-name>WNBC</display-name></channel>
        <programme channel="4.1" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>Some Show</title>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml)))

    await guide_xmltv.refresh_xmltv_guide()

    assert db.list_channels(True) == []
    assert db.list_xmltv_channel_map() == []


async def test_refresh_auto_maps_channel_by_exact_number_match(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    _configure_xmltv()
    now = time.time()
    xml = f"""<tv>
        <channel id="wnbc.us"><display-name>4.1</display-name><display-name>NBC New York</display-name></channel>
        <programme channel="wnbc.us" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>Some Show</title>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml)))

    await guide_xmltv.refresh_xmltv_guide()

    mapping = db.get_xmltv_channel_map("ch1")
    assert mapping is not None
    assert mapping["xmltv_channel_id"] == "wnbc.us"
    rows = db.list_guide_programs(["ch1"], now - 10, now + 3600)
    assert len(rows) == 1
    assert rows[0]["title"] == "Some Show"
    assert rows[0]["source_provider"] == "xmltv"


async def test_refresh_skips_unmapped_channels(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    _configure_xmltv()
    now = time.time()
    xml = f"""<tv>
        <channel id="other.us"><display-name>Other Channel</display-name></channel>
        <programme channel="other.us" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>Unmapped Show</title>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml)))

    await guide_xmltv.refresh_xmltv_guide()

    assert db.get_xmltv_channel_map("ch1") is None
    assert db.list_guide_programs(["ch1"], now - 10, now + 3600) == []


async def test_refresh_never_creates_channel_rows(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    _configure_xmltv()
    now = time.time()
    xml = f"""<tv>
        <channel id="4.1"><display-name>WNBC</display-name></channel>
        <channel id="9.1"><display-name>Unrelated</display-name></channel>
        <programme channel="4.1" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>Some Show</title>
        </programme>
        <programme channel="9.1" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>Unrelated Show</title>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml)))

    await guide_xmltv.refresh_xmltv_guide()

    assert [c["id"] for c in db.list_channels(True)] == ["ch1"]


async def test_refresh_never_overwrites_existing_map_row(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    db.upsert_xmltv_channel_map("ch1", "manually-mapped.us", "Manual")
    _configure_xmltv()
    now = time.time()
    xml = f"""<tv>
        <channel id="4.1"><display-name>WNBC</display-name></channel>
        <programme channel="4.1" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>Some Show</title>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml)))

    await guide_xmltv.refresh_xmltv_guide()

    mapping = db.get_xmltv_channel_map("ch1")
    assert mapping["xmltv_channel_id"] == "manually-mapped.us"
    # The auto-mapper never ran for this pre-mapped channel, so the "4.1"
    # programme (keyed to the auto-matched id, not the manual one) is unmapped.
    assert db.list_guide_programs(["ch1"], now - 10, now + 3600) == []


async def test_refresh_parses_rich_fields(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    _configure_xmltv()
    now = time.time()
    xml = f"""<tv>
        <channel id="4.1"><display-name>WNBC</display-name></channel>
        <programme channel="4.1" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>Some Show</title>
            <sub-title>The Pilot</sub-title>
            <desc>A show begins.</desc>
            <date>2020-01-01</date>
            <category>Drama</category>
            <category>Crime</category>
            <episode-num system="xmltv_ns">4.11.0/1</episode-num>
            <icon src="http://example.com/i.jpg" />
            <new/>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml)))

    await guide_xmltv.refresh_xmltv_guide()

    rows = db.list_guide_programs(["ch1"], now - 10, now + 3600)
    assert len(rows) == 1
    row = rows[0]
    assert row["episode_title"] == "The Pilot"
    assert row["synopsis"] == "A show begins."
    assert row["original_air_date"] == "2020-01-01"
    assert row["category"] == "Drama, Crime"
    assert row["season_number"] == 5
    assert row["episode_number"] == 12
    assert row["image_url"] == "http://example.com/i.jpg"
    assert row["is_new"] == 1


async def test_refresh_parses_onscreen_episode_num(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    _configure_xmltv()
    now = time.time()
    xml = f"""<tv>
        <channel id="4.1"><display-name>WNBC</display-name></channel>
        <programme channel="4.1" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>Some Show</title>
            <episode-num system="onscreen">S05E12</episode-num>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml)))

    await guide_xmltv.refresh_xmltv_guide()

    rows = db.list_guide_programs(["ch1"], now - 10, now + 3600)
    assert rows[0]["season_number"] == 5
    assert rows[0]["episode_number"] == 12


async def test_refresh_purges_stale_programs_on_rerefresh(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    _configure_xmltv()
    now = time.time()
    xml1 = f"""<tv>
        <channel id="4.1"><display-name>WNBC</display-name></channel>
        <programme channel="4.1" start="{_xmltv_time(now + 7200)}" stop="{_xmltv_time(now + 9000)}">
            <title>Old Show</title>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml1)))
    await guide_xmltv.refresh_xmltv_guide()

    xml2 = f"""<tv>
        <channel id="4.1"><display-name>WNBC</display-name></channel>
        <programme channel="4.1" start="{_xmltv_time(now + 10800)}" stop="{_xmltv_time(now + 12600)}">
            <title>New Show</title>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml2)))
    await guide_xmltv.refresh_xmltv_guide()

    rows = db.list_guide_programs(["ch1"], now - 10, now + 20000)
    assert {row["title"] for row in rows} == {"New Show"}


def test_parse_xmltv_time_returns_none_on_garbage():
    assert guide_xmltv._parse_xmltv_time("not-a-date") is None
    assert guide_xmltv._parse_xmltv_time(None) is None


def test_parse_episode_num_returns_none_on_unrecognized_format():
    el = ElementTree.fromstring(
        '<programme channel="x" start="1" stop="2"><episode-num>garbage</episode-num></programme>'
    )
    assert guide_xmltv._parse_episode_num(el) == (None, None)


async def test_refresh_leaves_existing_data_when_fetch_fails(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    _configure_xmltv()
    now = time.time()
    xml = f"""<tv>
        <channel id="4.1"><display-name>WNBC</display-name></channel>
        <programme channel="4.1" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>Some Show</title>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml)))
    await guide_xmltv.refresh_xmltv_guide()
    state_before = db.get_guide_provider_state(guide_xmltv.SOURCE_PROVIDER)

    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=None))
    await guide_xmltv.refresh_xmltv_guide()

    rows = db.list_guide_programs(["ch1"], now - 10, now + 3600)
    assert len(rows) == 1
    assert db.get_guide_provider_state(guide_xmltv.SOURCE_PROVIDER) == state_before


def test_parse_xmltv_time_supports_various_formats():
    from zoneinfo import ZoneInfo
    tz_chicago = ZoneInfo("America/Chicago")

    # 14 digits with +HH:MM
    ts1 = guide_xmltv._parse_xmltv_time("20260823190000 -05:00")
    assert ts1 is not None
    assert int(ts1) == 1787529600

    # 14 digits with +HHMM
    ts2 = guide_xmltv._parse_xmltv_time("20260823190000 -0500")
    assert ts2 == ts1

    # 14 digits with Z
    ts3 = guide_xmltv._parse_xmltv_time("20260824000000 Z")
    assert ts3 == ts1

    # 12 digits (no seconds)
    ts4 = guide_xmltv._parse_xmltv_time("202608231900 -0500")
    assert ts4 == ts1

    # ISO 8601 string
    ts5 = guide_xmltv._parse_xmltv_time("2026-08-23T19:00:00-05:00")
    assert ts5 == ts1

    # No timezone offset, fallback to default_tz
    ts6 = guide_xmltv._parse_xmltv_time("20260823190000", default_tz=tz_chicago)
    assert ts6 == ts1


async def test_refresh_parses_length_tag_when_stop_is_missing(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    _configure_xmltv()
    now = time.time()
    xml = f"""<tv>
        <channel id="4.1"><display-name>WNBC</display-name></channel>
        <programme channel="4.1" start="{_xmltv_time(now)}">
            <title>Show With Length</title>
            <length units="minutes">45</length>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml)))
    await guide_xmltv.refresh_xmltv_guide()

    rows = db.list_guide_programs(["ch1"], now - 10, now + 3600)
    assert len(rows) == 1
    assert rows[0]["title"] == "Show With Length"
    assert rows[0]["end_ts"] == rows[0]["start_ts"] + 45 * 60


async def test_refresh_auto_maps_by_display_name_prefix_and_callsign(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    db.upsert_channel("ch2", "7.1", "KABC", True)
    _configure_xmltv()
    now = time.time()
    xml = f"""<tv>
        <channel id="I4.1.xmltv.se"><display-name>4.1 WNBC-HD</display-name></channel>
        <channel id="kabc.station"><display-name>KABC</display-name></channel>
        <programme channel="I4.1.xmltv.se" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>WNBC Show</title>
        </programme>
        <programme channel="kabc.station" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>KABC Show</title>
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml)))
    await guide_xmltv.refresh_xmltv_guide()

    map1 = db.get_xmltv_channel_map("ch1")
    assert map1 is not None
    assert map1["xmltv_channel_id"] == "I4.1.xmltv.se"

    map2 = db.get_xmltv_channel_map("ch2")
    assert map2 is not None
    assert map2["xmltv_channel_id"] == "kabc.station"

    rows1 = db.list_guide_programs(["ch1"], now - 10, now + 3600)
    assert len(rows1) == 1
    assert rows1[0]["title"] == "WNBC Show"

    rows2 = db.list_guide_programs(["ch2"], now - 10, now + 3600)
    assert len(rows2) == 1
    assert rows2[0]["title"] == "KABC Show"


async def test_refresh_parses_audio_subtitles_and_subtitle(tmp_db, monkeypatch):
    db.upsert_channel("ch1", "3.1", "KTVK", True)
    _configure_xmltv()
    now = time.time()
    xml = f"""<tv>
        <channel id="3.1"><display-name>3.1</display-name><display-name>KTVK</display-name></channel>
        <programme channel="3.1" start="{_xmltv_time(now)}" stop="{_xmltv_time(now + 1800)}">
            <title>Inside Edition</title>
            <sub-title>Grandpa Boat Disaster</sub-title>
            <category>news</category>
            <audio><stereo>stereo</stereo></audio>
            <subtitles type="teletext"><language>en</language></subtitles>
            <new />
        </programme>
    </tv>"""
    monkeypatch.setattr(guide_xmltv, "_fetch_xmltv_root", AsyncMock(return_value=_root(xml)))
    await guide_xmltv.refresh_xmltv_guide()

    rows = db.list_guide_programs(["ch1"], now - 10, now + 3600)
    assert len(rows) == 1
    assert rows[0]["title"] == "Inside Edition"
    assert rows[0]["episode_title"] == "Grandpa Boat Disaster"
    assert rows[0]["audio"] == "stereo"
    assert rows[0]["has_subtitles"] == 1
    assert rows[0]["is_new"] == 1
    assert rows[0]["category"] == "news"


