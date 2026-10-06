from __future__ import annotations

import asyncio
import itertools
import time

import pytest

from app.dvr.builtin import comskip
from app.storage import db


class _FakeProcess:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.killed = False

    async def communicate(self):
        return b"", b""

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> None:
        pass


async def test_run_comskip_invokes_binary_with_ini_flag_not_bare_output_edl(monkeypatch, tmp_path):
    """Regression test: comskip has no "--output_edl" CLI flag at all (it's
    ini-only); passing it as a bare flag makes comskip reject the args and
    exit immediately before writing anything. EDL output must be requested
    via "--ini=<comskip.ini>" instead.
    """
    monkeypatch.setattr(comskip.shutil, "which", lambda name: "/usr/local/bin/comskip")

    captured_argv: list[tuple] = []

    async def fake_exec(*argv, **kwargs):
        captured_argv.append(argv)
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    video_path = tmp_path / "recording.ts"
    video_path.write_bytes(b"")

    ok = await comskip.run_comskip(video_path)

    assert ok is True
    assert len(captured_argv) == 1
    argv = captured_argv[0]
    assert argv[0] == "/usr/local/bin/comskip"
    assert "--output_edl" not in argv
    assert f"--ini={comskip.COMSKIP_INI_PATH}" in argv
    assert str(video_path) in argv
    assert str(video_path.parent) in argv


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


def test_resolve_hdhomerun_local_path_prefers_root_relative_path(tmp_path):
    (tmp_path / "Shows").mkdir()
    (tmp_path / "Shows" / "Episode.mpg").write_bytes(b"")

    path = comskip.resolve_hdhomerun_local_path(str(tmp_path), "Shows/Episode.mpg")

    assert path == (tmp_path / "Shows/Episode.mpg").resolve()


def test_resolve_hdhomerun_local_path_finds_basename_in_subfolder(tmp_path):
    (tmp_path / "Show").mkdir()
    (tmp_path / "Show" / "Episode.mpg").write_bytes(b"")

    path = comskip.resolve_hdhomerun_local_path(str(tmp_path), "Episode.mpg")

    assert path == (tmp_path / "Show" / "Episode.mpg").resolve()


def test_resolve_hdhomerun_local_path_returns_none_for_missing_basename(tmp_path):
    (tmp_path / "Show").mkdir()

    assert comskip.resolve_hdhomerun_local_path(str(tmp_path), "Episode.mpg") is None


def test_resolve_hdhomerun_local_path_returns_none_for_ambiguous_basename(tmp_path):
    for folder in ("A", "B"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "Episode.mpg").write_bytes(b"")

    assert comskip.resolve_hdhomerun_local_path(str(tmp_path), "Episode.mpg") is None


def test_resolve_hdhomerun_local_path_rejects_traversal_outside_root(tmp_path):
    path = comskip.resolve_hdhomerun_local_path(str(tmp_path), "../../etc/passwd")

    assert path is None


def _hdhomerun_entry(*, recording_id="hdhr_rec_1", filename="Episode.mpg", record_end=1.0):
    return {
        "recording_id": recording_id,
        "filename": filename,
        "record_end": record_end,
    }


async def test_hdhomerun_comskip_sweep_is_a_no_op_when_recordings_path_unset(tmp_db, monkeypatch):
    db.save_network_integration("hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local"})

    async def fake_fetch_dvr_recordings(settings):
        raise AssertionError("fetch_dvr_recordings should not be called when dvr_recordings_path is unset")

    monkeypatch.setattr("app.integrations.hdhomerun_client.fetch_dvr_recordings", fake_fetch_dvr_recordings)

    calls = []
    monkeypatch.setattr(comskip, "run_comskip", lambda path: calls.append(path))

    await comskip.run_comskip_sweep()

    assert calls == []


async def test_hdhomerun_comskip_sweep_runs_comskip_and_tracks_status(tmp_db, tmp_path, monkeypatch):
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_recordings_path": str(tmp_path)}
    )

    video_path = tmp_path / "Show" / "Episode.mpg"
    video_path.parent.mkdir(parents=True)
    video_path.write_bytes(b"")

    async def fake_fetch_dvr_recordings(settings):
        return [_hdhomerun_entry()]

    monkeypatch.setattr("app.integrations.hdhomerun_client.fetch_dvr_recordings", fake_fetch_dvr_recordings)

    calls = []

    async def fake_run_comskip(path):
        calls.append(path)
        return True

    monkeypatch.setattr(comskip, "run_comskip", fake_run_comskip)

    await comskip.run_comskip_sweep()

    assert calls == [video_path.resolve()]
    status = db.get_hdhomerun_comskip_status("hdhr_rec_1")
    assert status["status"] == "done"
    assert status["attempts"] == 1
    assert status["filename"] == "Episode.mpg"


async def test_hdhomerun_comskip_sweep_skips_recording_still_in_progress(tmp_db, tmp_path, monkeypatch):
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_recordings_path": str(tmp_path)}
    )

    future_end = time.time() + 3600

    async def fake_fetch_dvr_recordings(settings):
        return [_hdhomerun_entry(record_end=future_end)]

    monkeypatch.setattr("app.integrations.hdhomerun_client.fetch_dvr_recordings", fake_fetch_dvr_recordings)

    calls = []
    monkeypatch.setattr(comskip, "run_comskip", lambda path: calls.append(path))

    await comskip.run_comskip_sweep()

    assert calls == []
    assert db.get_hdhomerun_comskip_status("hdhr_rec_1") is None


async def test_hdhomerun_comskip_sweep_marks_skipped_when_global_mode_none(tmp_db, tmp_path, monkeypatch):
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_recordings_path": str(tmp_path)}
    )
    db.save_app_settings({"comskip_mode": "none"})

    async def fake_fetch_dvr_recordings(settings):
        return [_hdhomerun_entry()]

    monkeypatch.setattr("app.integrations.hdhomerun_client.fetch_dvr_recordings", fake_fetch_dvr_recordings)

    calls = []
    monkeypatch.setattr(comskip, "run_comskip", lambda path: calls.append(path))

    await comskip.run_comskip_sweep()

    assert calls == []
    status = db.get_hdhomerun_comskip_status("hdhr_rec_1")
    assert status["status"] == "skipped"


async def test_hdhomerun_comskip_sweep_skips_file_not_present_on_local_mount(tmp_db, tmp_path, monkeypatch):
    db.save_network_integration(
        "hdhomerun", "hdhomerun", "HDHomeRun", {"dvr_host": "dvr.local", "dvr_recordings_path": str(tmp_path)}
    )

    async def fake_fetch_dvr_recordings(settings):
        return [_hdhomerun_entry(filename="Missing.mpg")]

    monkeypatch.setattr("app.integrations.hdhomerun_client.fetch_dvr_recordings", fake_fetch_dvr_recordings)

    calls = []
    monkeypatch.setattr(comskip, "run_comskip", lambda path: calls.append(path))

    await comskip.run_comskip_sweep()

    assert calls == []
    status = db.get_hdhomerun_comskip_status("hdhr_rec_1")
    assert status["status"] == "failed"
    assert status["attempts"] == 1


async def test_hdhomerun_recordings_mount_check_reports_resolved_recordings(tmp_path, monkeypatch):
    (tmp_path / "Show").mkdir()
    (tmp_path / "Show" / "Episode.mpg").write_bytes(b"")

    async def fake_fetch_dvr_recordings(settings):
        return [_hdhomerun_entry(), _hdhomerun_entry(recording_id="x", filename="Gone.mpg")]

    monkeypatch.setattr("app.integrations.hdhomerun_client.fetch_dvr_recordings", fake_fetch_dvr_recordings)

    detail = await comskip.check_hdhomerun_recordings_mount({"dvr_recordings_path": str(tmp_path)})

    assert "1 of 2 DVR recordings found" in detail
    assert "'Gone.mpg'" in detail


async def test_hdhomerun_recordings_mount_check_fails_when_no_recording_resolves(tmp_path, monkeypatch):
    (tmp_path / "unrelated.txt").write_text("x")

    async def fake_fetch_dvr_recordings(settings):
        return [_hdhomerun_entry()]

    monkeypatch.setattr("app.integrations.hdhomerun_client.fetch_dvr_recordings", fake_fetch_dvr_recordings)

    from app.integrations.hdhomerun_client import HDHomeRunError

    with pytest.raises(HDHomeRunError, match="None of the 1 DVR recordings"):
        await comskip.check_hdhomerun_recordings_mount({"dvr_recordings_path": str(tmp_path)})


async def test_hdhomerun_recordings_mount_check_rejects_missing_directory(tmp_path):
    from app.integrations.hdhomerun_client import HDHomeRunError

    with pytest.raises(HDHomeRunError, match="is not a directory"):
        await comskip.check_hdhomerun_recordings_mount({"dvr_recordings_path": str(tmp_path / "nope")})


async def test_hdhomerun_recordings_mount_check_rejects_unwritable_directory(tmp_path, monkeypatch):
    from app.integrations.hdhomerun_client import HDHomeRunError

    (tmp_path / "Show").mkdir()
    (tmp_path / "Show" / "Episode.mpg").write_bytes(b"")

    def deny_write(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(comskip.tempfile, "NamedTemporaryFile", deny_write)

    with pytest.raises(HDHomeRunError, match="not writable"):
        await comskip.check_hdhomerun_recordings_mount({"dvr_recordings_path": str(tmp_path)})
