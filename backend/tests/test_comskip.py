from __future__ import annotations

import itertools

import pytest

from app.dvr.builtin import comskip
from app.storage import db


@pytest.mark.parametrize(
    "global_mode,rule_override,expected",
    [
        # rule override always wins, regardless of global_mode
        *((mode, "always", True) for mode in ("all", "none", "per_rule")),
        *((mode, "never", False) for mode in ("all", "none", "per_rule")),
        # 'default' defers to the global setting
        ("all", "default", True),
        ("per_rule", "default", True),
        ("none", "default", False),
    ],
)
def test_resolve_comskip_enabled_truth_table(global_mode, rule_override, expected):
    assert comskip.resolve_comskip_enabled(global_mode, rule_override) is expected


def test_resolve_comskip_enabled_covers_every_combination():
    modes = ("all", "none", "per_rule")
    overrides = ("default", "always", "never")
    for mode, override in itertools.product(modes, overrides):
        # Must not raise and must return a bool for every combination.
        assert isinstance(comskip.resolve_comskip_enabled(mode, override), bool)


def test_recording_rules_table_has_comskip_override_column(tmp_db):
    db.create_recording_rule(
        {
            "id": "rule_1",
            "provider": "builtin",
            "type": "series",
            "title": "Test Show",
        }
    )
    rule = db.get_recording_rule("rule_1")
    assert rule["comskip_override"] == "default"


def test_get_comskip_override_for_recording_follows_the_rule(tmp_db):
    db.create_recording_rule(
        {
            "id": "rule_1",
            "provider": "builtin",
            "type": "series",
            "title": "Test Show",
            "comskip_override": "always",
        }
    )
    db.upsert_scheduled_recording(
        {
            "id": "sched_1",
            "rule_id": "rule_1",
            "channel_id": "4.1",
            "title": "Test Show",
            "start_ts": 0.0,
            "end_ts": 3600.0,
            "status": "completed",
            "recording_id": "rec_1",
        }
    )
    db.create_recording(
        {
            "id": "rec_1",
            "scheduled_recording_id": "sched_1",
            "title": "Test Show",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 0.0,
            "file_path": "/tmp/rec_1.ts",
            "status": "completed",
        }
    )

    assert db.get_comskip_override_for_recording("rec_1") == "always"


def test_get_comskip_override_for_recording_defaults_for_manual_recording(tmp_db):
    db.create_recording(
        {
            "id": "rec_manual",
            "scheduled_recording_id": None,
            "title": "Manual Recording",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 0.0,
            "file_path": "/tmp/rec_manual.ts",
            "status": "completed",
        }
    )

    assert db.get_comskip_override_for_recording("rec_manual") == "default"


def test_get_comskip_override_for_recording_defaults_for_unknown_id(tmp_db):
    assert db.get_comskip_override_for_recording("does_not_exist") == "default"


def _create_completed_recording(tmp_path, recording_id: str, *, comskip_status: str, comskip_attempts: int) -> None:
    file_path = tmp_path / f"{recording_id}.ts"
    file_path.write_bytes(b"")
    db.create_recording(
        {
            "id": recording_id,
            "scheduled_recording_id": None,
            "title": "Test Recording",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 0.0,
            "file_path": str(file_path),
            "status": "completed",
            "comskip_status": comskip_status,
            "comskip_attempts": comskip_attempts,
        }
    )


async def test_run_comskip_sweep_retries_failed_recording_under_attempt_cap(tmp_db, tmp_path, monkeypatch):
    _create_completed_recording(
        tmp_path, "rec_retry", comskip_status="failed", comskip_attempts=comskip.MAX_COMSKIP_ATTEMPTS - 1
    )

    calls = []

    async def fake_run_comskip(path):
        calls.append(path)
        return True

    monkeypatch.setattr(comskip, "run_comskip", fake_run_comskip)

    await comskip.run_comskip_sweep()

    assert len(calls) == 1
    recording = db.get_recording("rec_retry")
    assert recording["comskip_status"] == "done"
    assert recording["comskip_attempts"] == comskip.MAX_COMSKIP_ATTEMPTS


async def test_run_comskip_sweep_skips_failed_recording_at_attempt_cap(tmp_db, tmp_path, monkeypatch):
    _create_completed_recording(
        tmp_path, "rec_exhausted", comskip_status="failed", comskip_attempts=comskip.MAX_COMSKIP_ATTEMPTS
    )

    calls = []

    async def fake_run_comskip(path):
        calls.append(path)
        return True

    monkeypatch.setattr(comskip, "run_comskip", fake_run_comskip)

    await comskip.run_comskip_sweep()

    assert calls == []
    recording = db.get_recording("rec_exhausted")
    assert recording["comskip_status"] == "failed"
    assert recording["comskip_attempts"] == comskip.MAX_COMSKIP_ATTEMPTS
