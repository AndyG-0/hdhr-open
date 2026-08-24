"""Runtime probes for the hardware-acceleration chain behind `server_transcode`.

Getting VAAPI/Quick Sync working from inside a container has a long chain of
independent prerequisites — the render node has to be passed through, be the
*right* node, be readable by the backend's uid, have a VA driver that loads,
and expose the specific profile/entrypoint the preset needs — and until this
module existed, every one of those failures collapsed into the same opaque
502 from `app/api/hdhomerun.py`. Worse, reproducing one meant a live tuner
and a channel that isn't already in use.

So each link gets probed independently and reported together:

* `process_identity()`   — who the backend actually runs as (the `group_add`
                           question)
* `list_render_devices()`— what's under /dev/dri and whether we can open it
                           (the passthrough question, and whether the node is
                           `renderD128` at all)
* `vainfo()`             — whether a VA driver loads and which
                           profiles/entrypoints it offers
* `ffmpeg_capabilities()`— whether this ffmpeg build even has the encoders
* `probe_transcode()`    — a real ~1s MPEG-2 transcode through the exact
                           preset args, no tuner required

Nothing here raises: a diagnostic that fails while diagnosing a failure is
useless, so every probe degrades to a structured "this didn't work, here's
the output" entry.
"""

from __future__ import annotations

import asyncio
import contextlib
import glob
import os
import re
import shlex
import stat
import sys
from typing import Any

from app import transcoding

DRI_DIR = "/dev/dri"

_COMMAND_TIMEOUT_SECONDS = 15
# Long enough that a cold GPU/driver init isn't mistaken for a failure, short
# enough that the /stream route's auto-probe doesn't noticeably delay the 502
# it's explaining. Transcoding a 1s clip is otherwise near-instant, so a probe
# anywhere near this limit is itself the finding.
_PROBE_TIMEOUT_SECONDS = 15
_SAMPLE_SECONDS = 3
# At 30fps this puts several GOPs in the clip, so a resync point still
# exists after _mpeg2_sample() truncates the lead-in (see its docstring).
_SAMPLE_GOP_SIZE = 15
# Probe output is verbose by design and ends up in both a log line and an
# HTTP body; keep it bounded.
_OUTPUT_LIMIT_CHARS = 6000

# `vainfo` profile lines look like:
#     VAProfileH264High               : VAEntrypointEncSlice
_VAINFO_PROFILE_RE = re.compile(r"^\s*(VAProfile\w+)\s*:\s*(VAEntrypoint\w+)\s*$")
_VAINFO_DRIVER_RE = re.compile(r"^\s*vainfo:\s*Driver version:\s*(.+?)\s*$")

# What the tuner's MPEG-2 needs to decode on the GPU, and what any of the
# H.264 presets need to encode there.
MPEG2_DECODE_ENTRYPOINT = ("VAProfileMPEG2Main", "VAEntrypointVLD")
H264_ENCODE_PROFILES = ("VAProfileH264High", "VAProfileH264Main", "VAProfileH264ConstrainedBaseline")
H264_ENCODE_ENTRYPOINTS = ("VAEntrypointEncSlice", "VAEntrypointEncSliceLP")


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) <= _OUTPUT_LIMIT_CHARS:
        return text
    return f"...(truncated)...\n{text[-_OUTPUT_LIMIT_CHARS:]}"


async def _run(argv: list[str], *, timeout: float = _COMMAND_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Run a command and capture everything it said, without ever raising.

    stderr is folded into stdout because for these tools it carries the
    interesting half — `vainfo`'s driver-load trace goes to stderr even on a
    successful run.
    """
    command = shlex.join(argv)
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        return {"command": command, "ok": False, "exit_code": None, "output": f"could not run {argv[0]}: {exc}"}

    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.kill()
        with contextlib.suppress(Exception):
            await process.wait()
        return {"command": command, "ok": False, "exit_code": None, "output": f"timed out after {timeout:g}s"}

    return {
        "command": command,
        "ok": process.returncode == 0,
        "exit_code": process.returncode,
        "output": _truncate(stdout.decode(errors="replace")),
    }


def process_identity() -> dict[str, Any]:
    """The uid/gid/supplementary groups ffmpeg will inherit.

    This is what settles the `group_add` question: /dev/dri/renderD128 is
    mode 660 root:render on the host, so the host's render GID has to appear
    in `groups` for the backend to open it. Note that a privileged container
    does *not* help here — a non-root process gets no effective capabilities
    from it, so CAP_DAC_OVERRIDE never applies.
    """
    return {
        "uid": os.getuid(),
        "gid": os.getgid(),
        "groups": sorted(os.getgroups()),
    }


def list_render_devices() -> dict[str, Any]:
    """Every DRM node visible to this process, with whether we can open it.

    Enumerating rather than checking the configured path alone is deliberate:
    when a host has a second DRM device the iGPU's render node shifts to
    `renderD129`, and the default `/dev/dri/renderD128` then points at
    nothing. That reads identically to "no passthrough" unless you can see
    what *is* there.
    """
    if not os.path.isdir(DRI_DIR):
        return {"dir_exists": False, "devices": []}

    devices = []
    for path in sorted(glob.glob(f"{DRI_DIR}/render*") + glob.glob(f"{DRI_DIR}/card*")):
        entry: dict[str, Any] = {"path": path}
        try:
            info = os.stat(path)
            entry.update(
                mode=stat.filemode(info.st_mode),
                owner_uid=info.st_uid,
                owner_gid=info.st_gid,
                # Both bits matter: VAAPI opens the render node read-write.
                readable=os.access(path, os.R_OK),
                writable=os.access(path, os.W_OK),
            )
        except OSError as exc:
            entry["error"] = str(exc)
        devices.append(entry)
    return {"dir_exists": True, "devices": devices}


async def vainfo(device: str) -> dict[str, Any]:
    """Which VA-API profiles/entrypoints the driver exposes for `device`.

    `vainfo` is bundled in the backend image precisely for this (see
    backend/Dockerfile). Its own stderr chatter ("libva info: Trying to open
    .../iHD_drv_video.so") is captured too — when the driver fails to load,
    that chatter *is* the diagnosis.
    """
    result = await _run(["vainfo", "--display", "drm", "--device", device])

    profiles: dict[str, list[str]] = {}
    driver = None
    for line in result["output"].splitlines():
        match = _VAINFO_PROFILE_RE.match(line)
        if match:
            profiles.setdefault(match.group(1), []).append(match.group(2))
            continue
        match = _VAINFO_DRIVER_RE.match(line)
        if match:
            driver = match.group(1)

    can_encode_h264 = any(
        entrypoint in profiles.get(profile, [])
        for profile in H264_ENCODE_PROFILES
        for entrypoint in H264_ENCODE_ENTRYPOINTS
    )
    return {
        **result,
        "device": device,
        "driver": driver,
        "profiles": profiles,
        "can_decode_mpeg2": MPEG2_DECODE_ENTRYPOINT[1] in profiles.get(MPEG2_DECODE_ENTRYPOINT[0], []),
        "can_encode_h264": can_encode_h264,
    }


async def ffmpeg_capabilities() -> dict[str, Any]:
    """Version, available hwaccels, and which hardware H.264 encoders are built in.

    Separates "this ffmpeg build has no h264_qsv" from "it has one but the
    GPU won't take it" — different fixes entirely (rebuild the image vs fix
    the device).
    """
    version, hwaccels, encoders = await asyncio.gather(
        _run(["ffmpeg", "-hide_banner", "-version"]),
        _run(["ffmpeg", "-hide_banner", "-hwaccels"]),
        _run(["ffmpeg", "-hide_banner", "-encoders"]),
    )
    hardware_encoders = sorted(
        {
            field
            for line in encoders["output"].splitlines()
            for field in line.split()
            if field.startswith("h264_") or field.startswith("hevc_")
        }
    )
    return {
        "version": version["output"].splitlines()[0] if version["ok"] and version["output"] else version["output"],
        "hwaccels": [line.strip() for line in hwaccels["output"].splitlines()[1:] if line.strip()],
        "hardware_encoders": hardware_encoders,
        "ffmpeg_available": version["ok"],
    }


async def _mpeg2_sample() -> tuple[bytes | None, str | None]:
    """A few-GOP MPEG-2/AC-3 transport stream, joined mid-stream like the tuner sends.

    Probing with `-f lavfi -i testsrc` directly would exercise the encoder
    but *not* the decoder, so a preset like `vaapi_full` — whose whole risk
    is whether the GPU can still hardware-decode MPEG-2 — would pass the
    probe and then fail on a real channel. Feeding real MPEG-2 in gets closer,
    but a clip that starts clean at frame 0 still isn't representative: a
    live tuner connection always joins mid-transport-stream, so the decoder
    never sees the very first sequence header and has to resync at the next
    GOP boundary instead. Some hardware MPEG-2 decoders handle that resync
    badly — corrupt/zero-dimension frames until they lock on, which has been
    observed to leave the downstream VAAPI encoder's coded-buffer sizing
    wrong and crash on the first real frame — and a clip starting at frame 0
    never exercises that path, so the probe passed while the same preset
    failed on every real channel. Building multiple GOPs and discarding the
    lead-in below reproduces the resync a live join forces.
    """
    argv = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostats",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=1280x720:rate=30:duration={_SAMPLE_SECONDS}",
        "-f",
        "lavfi",
        "-i",
        f"sine=frequency=440:duration={_SAMPLE_SECONDS}",
        "-c:v",
        "mpeg2video",
        "-g",
        str(_SAMPLE_GOP_SIZE),
        "-b:v",
        "4M",
        "-c:a",
        "ac3",
        "-f",
        "mpegts",
        "pipe:1",
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return None, f"could not run ffmpeg to build a test sample: {exc}"

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=_COMMAND_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        with contextlib.suppress(Exception):
            await process.wait()
        return None, "timed out building the MPEG-2 test sample"

    if process.returncode != 0 or not stdout:
        return None, _truncate(stderr.decode(errors="replace")) or "ffmpeg produced no test sample"

    # Drop the lead-in GOP so the probe never sees the clip's very first
    # sequence header, same as tuning into a channel already in progress.
    # The mpegts demuxer resyncs on the next 0x47 sync byte regardless of
    # where this cuts, and PAT/PMT repeat often enough in ffmpeg's muxer
    # output that a later copy is always still ahead in the remaining bytes.
    joined_mid_stream = stdout[len(stdout) // 4 :]
    return joined_mid_stream, None


async def probe_transcode(
    settings: dict[str, Any],
    *,
    sample: bytes | None = None,
) -> dict[str, Any]:
    """Run the widget's exact transcode settings against a synthetic channel.

    Deliberately routed through `transcoding.build_ffmpeg_args` rather than
    reassembling the arguments here, so the probe can never drift from what
    /stream actually runs — a probe that passes while the real thing fails
    would be worse than none. Only the input (a pipe instead of the tuner)
    and the log level (always verbose) differ.
    """
    probe_settings = {**settings, "ffmpeg_debug": True}
    try:
        args = transcoding.build_ffmpeg_args(probe_settings, "pipe:0")
    except transcoding.InvalidCustomFfmpegArgsError as exc:
        return {"ok": False, "command": None, "exit_code": None, "output": str(exc)}

    if sample is None:
        sample, error = await _mpeg2_sample()
        if sample is None:
            return {"ok": False, "command": None, "exit_code": None, "output": error or "no test sample"}

    # stdout is the transcoded stream; we only care that it was produced, so
    # discard it rather than buffering a megabyte of MPEG-TS per probe.
    argv = ["ffmpeg", *args]
    command = shlex.join(argv)
    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError as exc:
        return {"ok": False, "command": command, "exit_code": None, "output": f"could not run ffmpeg: {exc}"}

    try:
        _, stderr = await asyncio.wait_for(process.communicate(input=sample), timeout=_PROBE_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        with contextlib.suppress(Exception):
            await process.wait()
        return {
            "ok": False,
            "command": command,
            "exit_code": None,
            "output": f"timed out after {_PROBE_TIMEOUT_SECONDS}s",
        }

    return {
        "ok": process.returncode == 0,
        "command": command,
        "exit_code": process.returncode,
        "output": _truncate(stderr.decode(errors="replace")),
    }


def _probe_candidates(device: str, dri: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Which presets are worth test-encoding on *this* machine.

    Probing all of them everywhere would bury the two lines that matter under
    predictable failures — nvenc on a box with no NVIDIA card, VideoToolbox on
    Linux. Each hardware preset is gated on its platform actually being
    plausible, so anything that does show up as failing is a real finding.
    """
    # The fallback everything degrades to, so confirm it genuinely works
    # before the summary recommends it.
    candidates: dict[str, dict[str, Any]] = {transcoding.DEFAULT_PRESET: {"hwaccel": transcoding.DEFAULT_PRESET}}
    if any(entry["path"] == device for entry in dri["devices"]):
        for preset_id in ("vaapi", "vaapi_full", "qsv"):
            candidates[preset_id] = {"hwaccel": preset_id, "hwaccel_device": device}
    if os.path.exists("/dev/nvidiactl"):
        candidates["nvenc"] = {"hwaccel": "nvenc"}
    if sys.platform == "darwin":
        candidates["videotoolbox"] = {"hwaccel": "videotoolbox"}
    return candidates


def _summarize(
    device: str,
    identity: dict[str, Any],
    dri: dict[str, Any],
    va: dict[str, Any] | None,
    capabilities: dict[str, Any],
    probes: dict[str, dict[str, Any]],
    sample_error: str | None,
) -> list[str]:
    """Plain-English findings, ordered so the first one is the thing to fix.

    The report's raw sections are complete but not readable at a glance; this
    is what turns them into an answer.
    """
    findings: list[str] = []

    if not capabilities.get("ffmpeg_available"):
        findings.append("ffmpeg is not installed or not on PATH for the backend process — no transcoding is possible.")

    if not dri["dir_exists"]:
        findings.append(
            f"{DRI_DIR} does not exist in this container. Hardware acceleration cannot work without it — add "
            "`devices: - /dev/dri:/dev/dri` to the backend service in docker-compose.yml and recreate the container."
        )
        return findings

    paths = [entry["path"] for entry in dri["devices"]]
    render_nodes = [entry for entry in dri["devices"] if entry["path"].startswith(f"{DRI_DIR}/render")]
    if not render_nodes:
        findings.append(
            f"{DRI_DIR} exists but contains no render node (found: {', '.join(paths) or 'nothing'}). "
            "The host may have no GPU render device, or only the card node was passed through."
        )
        return findings

    configured = next((entry for entry in dri["devices"] if entry["path"] == device), None)
    if configured is None:
        available = ", ".join(entry["path"] for entry in render_nodes)
        findings.append(
            f"The configured device {device} does not exist. Available render nodes: {available}. "
            "Set the widget's 'Render device' setting to one of those."
        )
        return findings

    if not (configured.get("readable") and configured.get("writable")):
        findings.append(
            f"{device} exists but is not readable/writable by this process "
            f"(uid={identity['uid']}, groups={identity['groups']}); the device is {configured.get('mode')} "
            f"owned by uid={configured.get('owner_uid')} gid={configured.get('owner_gid')}. "
            f'Add the host\'s render group to the container: `group_add: - "{configured.get("owner_gid")}"` '
            "in docker-compose.yml. Note that `privileged: true` does not fix this on its own, because the "
            "backend runs as a non-root user."
        )
        return findings

    if va is not None and not va["ok"]:
        findings.append(
            f"The render device opened, but no VA-API driver loaded for {device}. This is usually a missing or "
            "mismatched driver — try setting LIBVA_DRIVER_NAME (iHD for Intel Gen8+, i965 for older Intel, "
            "radeonsi for AMD). See the vainfo output below."
        )
    elif va is not None:
        findings.append(f"VA-API driver loaded for {device}: {va.get('driver') or 'unknown version'}.")
        if not va["can_encode_h264"]:
            findings.append(
                "The driver reports no H.264 encode entrypoint, so no VAAPI/QSV preset can work on this GPU. "
                "Use a software preset."
            )
        if not va["can_decode_mpeg2"]:
            findings.append(
                "The driver reports no MPEG-2 decode entrypoint. That is expected on newer Intel GPUs and is "
                'exactly why the "VAAPI" preset decodes in software — but it means the '
                '"VAAPI, full hardware decode + encode" preset cannot work here.'
            )

    if sample_error:
        findings.append(f"Could not build an MPEG-2 test clip, so no preset could be test-encoded: {sample_error}")
        return findings

    working = sorted(preset_id for preset_id, result in probes.items() if result.get("ok"))
    failing = sorted(preset_id for preset_id, result in probes.items() if not result.get("ok"))
    if working:
        findings.append(f"Presets that successfully transcoded a test stream: {', '.join(working)}.")
    if failing:
        findings.append(f"Presets that failed the test transcode: {', '.join(failing)}. See their output below.")
    return findings


async def full_report(device: str | None = None, extra_settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything above, in one payload, with a plain-English summary on top.

    `extra_settings` probes the widget's own saved settings alongside the
    stock presets — the only way to cover a "custom" preset's arguments.
    """
    device = device or transcoding.DEFAULT_HWACCEL_DEVICE
    identity = process_identity()
    dri = list_render_devices()
    capabilities = await ffmpeg_capabilities()

    # Skip the driver query when there's no device to query — it would just
    # restate the finding the DRI section already made.
    va = await vainfo(device) if any(entry["path"] == device for entry in dri["devices"]) else None

    probes: dict[str, dict[str, Any]] = {}
    sample_error: str | None = None
    if capabilities.get("ffmpeg_available"):
        sample, sample_error = await _mpeg2_sample()
        if sample is not None:
            candidates = _probe_candidates(device, dri)
            if extra_settings:
                candidates["current settings"] = {"hwaccel_device": device, **extra_settings}
            # Sequentially, not gathered: concurrent probes contend for the
            # same encoder session and can fail each other, which would make
            # a working GPU look broken.
            for name, probe_settings in candidates.items():
                probes[name] = await probe_transcode(probe_settings, sample=sample)

    return {
        "device": device,
        "process": identity,
        "dri": dri,
        "ffmpeg": capabilities,
        "vainfo": va,
        "probes": probes,
        "sample_error": sample_error,
        "summary": _summarize(device, identity, dri, va, capabilities, probes, sample_error),
    }
