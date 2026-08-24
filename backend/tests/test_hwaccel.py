from __future__ import annotations

import asyncio
import os

import pytest

from app import hwaccel

VAINFO_OUTPUT = """\
libva info: VA-API version 1.17.0
libva info: Trying to open /usr/lib/x86_64-linux-gnu/dri/iHD_drv_video.so
vainfo: VA-API version: 1.17 (libva 2.12.0)
vainfo: Driver version: Intel iHD driver for Intel(R) Gen Graphics - 23.1.1
vainfo: Supported profile and entrypoints
      VAProfileH264Main               : VAEntrypointVLD
      VAProfileH264High               : VAEntrypointVLD
      VAProfileH264High               : VAEntrypointEncSliceLP
      VAProfileJPEGBaseline           : VAEntrypointVLD
"""


class _FakeProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.killed = False

    async def communicate(self, input: bytes | None = None):
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        return self.returncode


def _char_device(gid: int) -> os.stat_result:
    return os.stat_result((0o020660, 0, 0, 1, 0, gid, 0, 0, 0, 0))


def _fake_dri(monkeypatch, paths: list[str], *, readable: bool = True, gid: int = 993) -> None:
    """Pretend /dev/dri holds exactly `paths`, each a mode-660 root:gid node.

    Every fake delegates to the real call for paths it doesn't own — these
    patch module-level `os`/`glob`, so a blanket answer would also be given
    to anything else running during the test.
    """
    real_isdir, real_stat, real_access = os.path.isdir, os.stat, os.access

    monkeypatch.setattr(hwaccel.os.path, "isdir", lambda p: True if p == hwaccel.DRI_DIR else real_isdir(p))
    monkeypatch.setattr(
        hwaccel.glob,
        "glob",
        lambda pattern: [p for p in paths if p.startswith(pattern.rstrip("*"))],
    )
    monkeypatch.setattr(hwaccel.os, "stat", lambda p: _char_device(gid) if p in paths else real_stat(p))
    monkeypatch.setattr(hwaccel.os, "access", lambda p, mode: readable if p in paths else real_access(p, mode))


def _linux_without_nvidia(monkeypatch) -> None:
    """Pin the platform gating in `_probe_candidates` so its output is deterministic."""
    real_exists = os.path.exists
    monkeypatch.setattr(hwaccel.os.path, "exists", lambda p: False if p == "/dev/nvidiactl" else real_exists(p))
    monkeypatch.setattr(hwaccel.sys, "platform", "linux")


def test_process_identity_reports_uid_gid_and_groups():
    identity = hwaccel.process_identity()

    assert identity["uid"] == os.getuid()
    assert identity["groups"] == sorted(os.getgroups())


def test_list_render_devices_reports_a_missing_dri_dir(monkeypatch):
    real_isdir = os.path.isdir
    monkeypatch.setattr(hwaccel.os.path, "isdir", lambda p: False if p == hwaccel.DRI_DIR else real_isdir(p))

    assert hwaccel.list_render_devices() == {"dir_exists": False, "devices": []}


def test_list_render_devices_reports_permissions(monkeypatch):
    _fake_dri(monkeypatch, ["/dev/dri/renderD128", "/dev/dri/card0"], readable=False)

    result = hwaccel.list_render_devices()

    assert [entry["path"] for entry in result["devices"]] == ["/dev/dri/card0", "/dev/dri/renderD128"]
    assert all(entry["readable"] is False for entry in result["devices"])
    assert result["devices"][0]["mode"] == "crw-rw----"
    assert result["devices"][0]["owner_gid"] == 993


async def test_vainfo_parses_profiles_and_capabilities(monkeypatch):
    async def fake_exec(*argv, **kwargs):
        assert argv[0] == "vainfo"
        assert "/dev/dri/renderD128" in argv
        return _FakeProcess(stdout=VAINFO_OUTPUT.encode())

    monkeypatch.setattr(hwaccel.asyncio, "create_subprocess_exec", fake_exec)

    result = await hwaccel.vainfo("/dev/dri/renderD128")

    assert result["driver"].startswith("Intel iHD driver")
    assert result["profiles"]["VAProfileH264High"] == ["VAEntrypointVLD", "VAEntrypointEncSliceLP"]
    assert result["can_encode_h264"] is True
    # This driver lists no VAProfileMPEG2Main at all — the exact case that
    # makes vaapi_full unusable while the plain vaapi preset still works.
    assert result["can_decode_mpeg2"] is False


async def test_vainfo_survives_a_missing_binary(monkeypatch):
    async def fake_exec(*argv, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "vainfo")

    monkeypatch.setattr(hwaccel.asyncio, "create_subprocess_exec", fake_exec)

    result = await hwaccel.vainfo("/dev/dri/renderD128")

    assert result["ok"] is False
    assert "could not run vainfo" in result["output"]
    # Still shaped like a report, so the caller doesn't have to special-case it.
    assert result["profiles"] == {}
    assert result["can_encode_h264"] is False


async def test_probe_transcode_runs_what_the_stream_route_would(monkeypatch):
    captured: list[tuple[str, ...]] = []

    async def fake_exec(*argv, **kwargs):
        captured.append(argv)
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(hwaccel.asyncio, "create_subprocess_exec", fake_exec)

    result = await hwaccel.probe_transcode({"hwaccel": "vaapi"}, sample=b"fake-mpegts")

    assert result["ok"] is True
    argv = list(captured[0])
    # Same preset the widget is configured with, fed from a pipe instead of
    # a tuner — a probe that diverged from /stream could pass while the real
    # thing fails.
    assert argv[argv.index("-i") + 1] == "pipe:0"
    assert "h264_vaapi" in argv
    assert "hwupload" in argv[argv.index("-vf") + 1]
    # Always verbose, whatever the widget's own log level is, so the failure
    # reason is actually in the captured output.
    assert argv[argv.index("-loglevel") + 1] == "verbose"


async def test_probe_transcode_reports_a_failed_encode(monkeypatch):
    async def fake_exec(*argv, **kwargs):
        return _FakeProcess(stderr=b"[AVHWDeviceContext] Failed to initialise VAAPI connection: -1.\n", returncode=1)

    monkeypatch.setattr(hwaccel.asyncio, "create_subprocess_exec", fake_exec)

    result = await hwaccel.probe_transcode({"hwaccel": "vaapi"}, sample=b"fake-mpegts")

    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert "Failed to initialise VAAPI connection" in result["output"]


async def test_probe_transcode_reports_unparseable_custom_args():
    result = await hwaccel.probe_transcode(
        {"hwaccel": "custom", "custom_ffmpeg_args": '-c:v "libx264'}, sample=b"fake-mpegts"
    )

    assert result["ok"] is False
    assert "Invalid custom ffmpeg arguments" in result["output"]


def test_probe_candidates_cover_every_gpu_preset_for_the_configured_device(monkeypatch):
    _linux_without_nvidia(monkeypatch)
    dri = {"dir_exists": True, "devices": [{"path": "/dev/dri/renderD128"}]}

    candidates = hwaccel._probe_candidates("/dev/dri/renderD128", dri)

    assert set(candidates) == {"software", "vaapi", "vaapi_full", "qsv"}
    assert candidates["vaapi"]["hwaccel_device"] == "/dev/dri/renderD128"


def test_probe_candidates_skip_vaapi_when_the_configured_device_is_absent(monkeypatch):
    _linux_without_nvidia(monkeypatch)
    dri = {"dir_exists": True, "devices": [{"path": "/dev/dri/renderD129"}]}

    candidates = hwaccel._probe_candidates("/dev/dri/renderD128", dri)

    # Nothing to gain from test-encoding through a device that isn't there;
    # the summary already names that as the problem.
    assert set(candidates) == {"software"}


def _summarize(device: str, dri: dict, va: dict | None = None, probes: dict | None = None) -> list[str]:
    return hwaccel._summarize(
        device,
        {"uid": 1000, "gid": 1000, "groups": [1000]},
        dri,
        va,
        {"ffmpeg_available": True},
        probes or {},
        None,
    )


@pytest.mark.parametrize(
    ("dri", "expected"),
    [
        ({"dir_exists": False, "devices": []}, "does not exist in this container"),
        ({"dir_exists": True, "devices": [{"path": "/dev/dri/card0"}]}, "contains no render node"),
    ],
)
def test_summary_names_a_broken_passthrough(dri, expected):
    findings = _summarize("/dev/dri/renderD128", dri)

    assert expected in findings[0]


def test_summary_points_at_the_render_node_that_does_exist():
    dri = {
        "dir_exists": True,
        "devices": [{"path": "/dev/dri/renderD129", "readable": True, "writable": True}],
    }

    findings = _summarize("/dev/dri/renderD128", dri)

    # A second DRM device shifts the iGPU to renderD129, which otherwise
    # reads exactly like "no passthrough at all".
    assert "The configured device /dev/dri/renderD128 does not exist." in findings[0]
    assert "/dev/dri/renderD129" in findings[0]


def test_summary_gives_the_exact_group_add_line_for_a_permission_failure():
    dri = {
        "dir_exists": True,
        "devices": [
            {
                "path": "/dev/dri/renderD128",
                "mode": "crw-rw----",
                "owner_uid": 0,
                "owner_gid": 993,
                "readable": False,
                "writable": False,
            }
        ],
    }

    findings = _summarize("/dev/dri/renderD128", dri)

    assert 'group_add: - "993"' in findings[0]
    # The trap that makes this failure so persistent: `privileged: true`
    # looks like it should fix a permission error, and doesn't, because the
    # backend runs as a non-root user.
    assert "`privileged: true` does not fix this" in findings[0]


def test_summary_explains_a_missing_mpeg2_decoder():
    dri = {
        "dir_exists": True,
        "devices": [{"path": "/dev/dri/renderD128", "readable": True, "writable": True}],
    }
    va = {"ok": True, "driver": "iHD 23.1.1", "can_encode_h264": True, "can_decode_mpeg2": False}

    findings = "\n".join(
        _summarize("/dev/dri/renderD128", dri, va, {"vaapi": {"ok": True}, "vaapi_full": {"ok": False}})
    )

    assert "no MPEG-2 decode entrypoint" in findings
    assert "Presets that successfully transcoded a test stream: vaapi." in findings
    assert "Presets that failed the test transcode: vaapi_full." in findings


def test_summary_blames_the_driver_when_the_device_opens_but_vainfo_fails():
    dri = {
        "dir_exists": True,
        "devices": [{"path": "/dev/dri/renderD128", "readable": True, "writable": True}],
    }
    va = {"ok": False, "driver": None, "can_encode_h264": False, "can_decode_mpeg2": False}

    findings = _summarize("/dev/dri/renderD128", dri, va)

    assert "no VA-API driver loaded" in findings[0]
    assert "LIBVA_DRIVER_NAME" in findings[0]


async def test_full_report_probes_every_preset_one_at_a_time(monkeypatch):
    _fake_dri(monkeypatch, ["/dev/dri/renderD128"])
    _linux_without_nvidia(monkeypatch)

    state = {"running": 0, "peak": 0}

    class _TrackingProcess(_FakeProcess):
        async def communicate(self, input: bytes | None = None):
            state["running"] += 1
            state["peak"] = max(state["peak"], state["running"])
            await asyncio.sleep(0)
            state["running"] -= 1
            return await super().communicate(input)

    async def fake_exec(*argv, **kwargs):
        if argv[0] == "vainfo":
            return _FakeProcess(stdout=VAINFO_OUTPUT.encode())
        if "pipe:0" in argv:
            return _TrackingProcess(returncode=0)
        return _FakeProcess(stdout=b"fake-mpegts-sample", returncode=0)

    monkeypatch.setattr(hwaccel.asyncio, "create_subprocess_exec", fake_exec)

    report = await hwaccel.full_report()

    assert report["device"] == "/dev/dri/renderD128"
    assert set(report["probes"]) == {"software", "vaapi", "vaapi_full", "qsv"}
    assert all(probe["ok"] for probe in report["probes"].values())
    # Concurrent probes contend for the same encoder session and can fail
    # each other, which would report a working GPU as broken.
    assert state["peak"] == 1
    assert report["vainfo"]["can_encode_h264"] is True
    assert report["summary"]


async def test_full_report_probes_the_widgets_own_settings_too(monkeypatch):
    _fake_dri(monkeypatch, ["/dev/dri/renderD128"])
    _linux_without_nvidia(monkeypatch)
    commands: list[tuple[str, ...]] = []

    async def fake_exec(*argv, **kwargs):
        commands.append(argv)
        if argv[0] == "vainfo":
            return _FakeProcess(stdout=VAINFO_OUTPUT.encode())
        return _FakeProcess(stdout=b"fake-mpegts-sample", returncode=0)

    monkeypatch.setattr(hwaccel.asyncio, "create_subprocess_exec", fake_exec)

    report = await hwaccel.full_report(extra_settings={"hwaccel": "custom", "custom_ffmpeg_args": "-c:v h264_v4l2m2m"})

    # The stock presets can't cover a "custom" args string; probing the saved
    # settings as well is the only way that path gets tested.
    assert "current settings" in report["probes"]
    assert any("h264_v4l2m2m" in argv for argv in commands)


async def test_full_report_uses_an_explicit_device_for_the_probes(monkeypatch):
    _fake_dri(monkeypatch, ["/dev/dri/renderD128", "/dev/dri/renderD129"])
    _linux_without_nvidia(monkeypatch)
    commands: list[tuple[str, ...]] = []

    async def fake_exec(*argv, **kwargs):
        commands.append(argv)
        if argv[0] == "vainfo":
            return _FakeProcess(stdout=VAINFO_OUTPUT.encode())
        return _FakeProcess(stdout=b"fake-mpegts-sample", returncode=0)

    monkeypatch.setattr(hwaccel.asyncio, "create_subprocess_exec", fake_exec)

    report = await hwaccel.full_report("/dev/dri/renderD129")

    assert report["device"] == "/dev/dri/renderD129"
    vaapi = next(argv for argv in commands if "h264_vaapi" in argv and "-vaapi_device" in argv)
    assert vaapi[vaapi.index("-vaapi_device") + 1] == "/dev/dri/renderD129"


async def test_full_report_without_ffmpeg_skips_probing(monkeypatch):
    _fake_dri(monkeypatch, ["/dev/dri/renderD128"])

    async def fake_exec(*argv, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", argv[0])

    monkeypatch.setattr(hwaccel.asyncio, "create_subprocess_exec", fake_exec)

    report = await hwaccel.full_report()

    assert report["probes"] == {}
    assert "ffmpeg is not installed" in report["summary"][0]


async def test_full_report_reports_a_device_it_cannot_open(monkeypatch):
    _fake_dri(monkeypatch, ["/dev/dri/renderD128"], readable=False)
    _linux_without_nvidia(monkeypatch)

    async def fake_exec(*argv, **kwargs):
        if argv[0] == "vainfo":
            return _FakeProcess(stdout=b"libva error: /dev/dri/renderD128: permission denied\n", returncode=1)
        return _FakeProcess(stdout=b"fake-mpegts-sample", returncode=0)

    monkeypatch.setattr(hwaccel.asyncio, "create_subprocess_exec", fake_exec)

    report = await hwaccel.full_report()

    assert report["dri"]["devices"][0]["readable"] is False
    assert 'group_add: - "993"' in report["summary"][0]
