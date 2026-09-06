from __future__ import annotations

from app.storage import db


def test_upsert_channel_creates_row(tmp_db):
    db.upsert_channel("ch1", "4.1", "WNBC", True)

    channel = db.get_channel("ch1")

    assert channel["channel_number"] == "4.1"
    assert channel["name"] == "WNBC"
    assert channel["is_hd"] == 1
    assert channel["is_favorite"] == 0
    assert channel["hidden"] == 0


def test_upsert_channel_preserves_user_edits_on_existing_row(tmp_db):
    db.upsert_channel("ch1", "4.1", "WNBC", True)
    db.update_channel("ch1", is_favorite=1, hidden=1, sort_order=5)

    # Simulate a subsequent guide-refresh cycle re-syncing tuner-sourced fields.
    db.upsert_channel("ch1", "4.1", "WNBC HD", True)

    channel = db.get_channel("ch1")

    assert channel["name"] == "WNBC HD"
    assert channel["is_favorite"] == 1
    assert channel["hidden"] == 1
    assert channel["sort_order"] == 5


def test_get_channel_by_number_returns_none_when_missing(tmp_db):
    assert db.get_channel_by_number("99.9") is None


def test_get_channel_by_number_finds_existing(tmp_db):
    db.upsert_channel("ch1", "4.1", "WNBC", True)

    channel = db.get_channel_by_number("4.1")

    assert channel["id"] == "ch1"


def _row(channel_id: str, provider: str, start_ts: float, title: str) -> dict:
    return {
        "channel_id": channel_id,
        "source_provider": provider,
        "external_program_id": None,
        "title": title,
        "episode_title": None,
        "season_number": None,
        "episode_number": None,
        "synopsis": None,
        "start_ts": start_ts,
        "end_ts": start_ts + 1800,
        "original_air_date": None,
        "image_url": None,
        "is_new": 0,
        "category": None,
    }


def test_resolve_guide_programs_prefers_pinned_provider(tmp_db):
    channels = [{"id": "ch1", "guide_provider": "hdhomerun_cloud"}]
    rows = [_row("ch1", "hdhomerun_cloud", 100, "Cloud Show"), _row("ch1", "xmltv", 100, "XMLTV Show")]

    resolved = db.resolve_guide_programs(channels, rows)

    assert [r["title"] for r in resolved["ch1"]] == ["Cloud Show"]


def test_resolve_guide_programs_falls_back_to_default_priority_when_unpinned(tmp_db):
    channels = [{"id": "ch1", "guide_provider": None}]
    rows = [_row("ch1", "xmltv", 100, "XMLTV Show"), _row("ch1", "hdhomerun_cloud", 100, "Cloud Show")]

    resolved = db.resolve_guide_programs(channels, rows)

    assert [r["title"] for r in resolved["ch1"]] == ["XMLTV Show"]


def test_resolve_guide_programs_falls_back_to_hdhomerun_when_external_providers_have_no_rows(tmp_db):
    channels = [{"id": "ch1", "guide_provider": None}]
    rows = [_row("ch1", "hdhomerun_cloud", 100, "Cloud Show")]

    resolved = db.resolve_guide_programs(channels, rows)

    assert [r["title"] for r in resolved["ch1"]] == ["Cloud Show"]


def test_resolve_guide_programs_falls_back_when_pinned_provider_has_no_rows(tmp_db):
    channels = [{"id": "ch1", "guide_provider": "xmltv"}]
    rows = [_row("ch1", "hdhomerun_cloud", 100, "Cloud Show")]

    resolved = db.resolve_guide_programs(channels, rows)

    assert [r["title"] for r in resolved["ch1"]] == ["Cloud Show"]


def test_resolve_guide_programs_omits_channels_with_no_rows(tmp_db):
    channels = [{"id": "ch1", "guide_provider": None}]

    resolved = db.resolve_guide_programs(channels, [])

    assert resolved == {}


def test_resolve_guide_programs_sorts_by_start_ts(tmp_db):
    channels = [{"id": "ch1", "guide_provider": None}]
    rows = [
        _row("ch1", "hdhomerun_cloud", 200, "Later Show"),
        _row("ch1", "hdhomerun_cloud", 100, "Earlier Show"),
    ]

    resolved = db.resolve_guide_programs(channels, rows)

    assert [r["title"] for r in resolved["ch1"]] == ["Earlier Show", "Later Show"]


def test_resolve_guide_programs_enriches_series_id_from_hdhomerun_cloud(tmp_db):
    channels = [{"id": "ch1", "guide_provider": None}]
    xml_row = _row("ch1", "xmltv", 100, "Jeopardy!")
    xml_row["external_program_id"] = None
    xml_row["image_url"] = None

    cloud_row = _row("ch1", "hdhomerun_cloud", 100, "Jeopardy!")
    cloud_row["external_program_id"] = "EP_JEOPARDY_123"
    cloud_row["image_url"] = "https://img.hdhomerun.com/titles/jeopardy.jpg"
    cloud_row["synopsis"] = "Contestants answer trivia questions."

    resolved = db.resolve_guide_programs(channels, [xml_row, cloud_row], default_priority=("xmltv", "hdhomerun_cloud"))

    assert len(resolved["ch1"]) == 1
    enriched = resolved["ch1"][0]
    assert enriched["title"] == "Jeopardy!"
    assert enriched["source_provider"] == "xmltv"
    assert enriched["external_program_id"] == "EP_JEOPARDY_123"
    assert enriched["image_url"] == "https://img.hdhomerun.com/titles/jeopardy.jpg"
    assert enriched["synopsis"] == "Contestants answer trivia questions."

