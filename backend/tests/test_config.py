from __future__ import annotations

from app import config


def test_effective_settings_falls_back_to_env_defaults(tmp_db):
    result = config.effective_settings()
    assert result["timezone"] == config.settings.timezone


def test_effective_settings_layers_db_overrides_on_top(tmp_db):
    from app.storage import db

    db.save_app_settings({"timezone": "America/Chicago"})

    result = config.effective_settings()
    assert result["timezone"] == "America/Chicago"


def test_resolve_timezone_falls_back_to_utc_for_unrecognized_name():
    from zoneinfo import ZoneInfo

    assert config.resolve_timezone("not/a/real/zone") == ZoneInfo("UTC")


def test_resolve_timezone_returns_matching_zone():
    from zoneinfo import ZoneInfo

    assert config.resolve_timezone("America/Chicago") == ZoneInfo("America/Chicago")


def test_resolve_guide_provider_priority():
    # Defaults
    assert config.resolve_guide_provider_priority("xmltv,schedules_direct,hdhomerun_cloud") == (
        "xmltv",
        "schedules_direct",
        "hdhomerun_cloud",
    )
    # Custom ordering
    assert config.resolve_guide_provider_priority("hdhomerun_cloud,xmltv,schedules_direct") == (
        "hdhomerun_cloud",
        "xmltv",
        "schedules_direct",
    )
    # Partial list appends missing valid providers
    assert config.resolve_guide_provider_priority("schedules_direct") == (
        "schedules_direct",
        "xmltv",
        "hdhomerun_cloud",
    )
    # Invalid names filtered out
    assert config.resolve_guide_provider_priority("invalid,hdhomerun_cloud") == (
        "hdhomerun_cloud",
        "xmltv",
        "schedules_direct",
    )


def test_resolve_dvr_server_priority():
    # Defaults
    assert config.resolve_dvr_server_priority("builtin,hdhomerun") == (
        "builtin",
        "hdhomerun",
    )
    # Custom ordering
    assert config.resolve_dvr_server_priority("hdhomerun,builtin") == (
        "hdhomerun",
        "builtin",
    )
    # Partial list appends missing valid servers
    assert config.resolve_dvr_server_priority("hdhomerun") == (
        "hdhomerun",
        "builtin",
    )
    # Invalid names filtered out
    assert config.resolve_dvr_server_priority("invalid,hdhomerun") == (
        "hdhomerun",
        "builtin",
    )
