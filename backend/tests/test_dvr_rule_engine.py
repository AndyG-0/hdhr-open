from __future__ import annotations

from unittest.mock import AsyncMock

from app.api.dvr_rules import RecordingRuleCreateRequest
from app.dvr import rule_engine
from app.integrations import hdhomerun_client
from app.storage import db


async def test_create_rule_with_fallback_returns_none_when_preferred_engine_accepts(tmp_db, monkeypatch):
    """Locks in the app.dvr.rule_engine extraction directly: when the
    preferred (highest-priority) engine accepts the rule, no fallback
    happened, so the function must report that with a None reason - the
    thin dvr_rules.create_recording_rule route relies on this to decide
    whether to set the X-DVR-Fallback response headers at all."""
    mock_add = AsyncMock(
        return_value=[{"RecordingRuleID": "off_1", "SeriesID": "SH123", "Provider": "hdhomerun"}]
    )
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    payload = RecordingRuleCreateRequest(series_id="SH123", channel="4.1", date_time=1725465600)
    settings = {"tuner_host": "hdhomerun.local", "dvr_host": "dvr.local", "dvr_port": 50000}

    reason = await rule_engine.create_rule_with_fallback(payload, settings, ["hdhomerun", "builtin"])

    assert reason is None
    assert mock_add.called


async def test_create_rule_with_fallback_falls_back_to_builtin_and_returns_reason(tmp_db, monkeypatch):
    """When the preferred engine (official HDHomeRun DVR) rejects the rule,
    create_rule_with_fallback must create it on the next engine in
    `priority` (builtin) instead, and surface the rejection reason so the
    route can set it as a response header - exercising the same fallback
    loop that used to live inline in dvr_rules.create_recording_rule."""
    mock_add = AsyncMock(side_effect=hdhomerun_client.HDHomeRunError("Add recording rule failed: Airing not found"))
    monkeypatch.setattr(hdhomerun_client, "add_recording_rule", mock_add)

    payload = RecordingRuleCreateRequest(series_id="SH123", channel="4.1", date_time=1725465600)
    settings = {"tuner_host": "hdhomerun.local", "dvr_host": "dvr.local", "dvr_port": 50000}

    reason = await rule_engine.create_rule_with_fallback(payload, settings, ["hdhomerun", "builtin"])

    assert reason is not None
    assert "Airing not found" in reason
    rules = db.list_recording_rules()
    assert len(rules) == 1
    assert rules[0]["provider"] == "builtin"


async def test_create_rule_with_fallback_raises_for_unsatisfiable_keyword_rule_on_hdhomerun(tmp_db):
    """A keyword/contains-match rule is builtin-only - pinning it to the
    official DVR via `server="hdhomerun"` has no engine that can satisfy it,
    so this must raise rather than silently creating nothing."""
    import pytest
    from fastapi import HTTPException

    payload = RecordingRuleCreateRequest(keyword_query="weather", server="hdhomerun")
    settings = {"tuner_host": "hdhomerun.local", "dvr_host": "dvr.local", "dvr_port": 50000}

    with pytest.raises(HTTPException) as exc_info:
        await rule_engine.create_rule_with_fallback(payload, settings, ["hdhomerun", "builtin"])

    assert exc_info.value.status_code == 400
