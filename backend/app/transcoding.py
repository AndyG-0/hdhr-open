"""ffmpeg transcode presets for HDHomeRun `server_transcode` playback.

Turning the tuner's raw MPEG-2 stream into browser-playable H.264/AAC needs
`ffmpeg`, and the fastest way to do that depends entirely on what hardware
the *backend* happens to run on — a software encode that's fine on a
desktop CPU can pin a Raspberry Pi, a hardware encoder that's free on one
box (Intel Quick Sync) doesn't exist on another (Apple Silicon, a plain ARM
SBC), and there's no single "auto-detect" ffmpeg build/driver setup that
covers all of them. The presets below cover the combinations this project
is actually deployed on or tested against; "custom" is the escape hatch for
anything else (a different GPU, a tuned bitrate, etc).

Each preset splits into `input_args` (placed before `-i`, needed for
hwaccel decode setup) and `output_args` (placed after it, before the fixed
`-f mpegts pipe:1` framing that the /stream route always appends — the
container and transport are structural, not something a preset should be
able to change).

Any `{device}` in either list is substituted with the widget's
`hwaccel_device` setting at build time. The render node isn't always
`/dev/dri/renderD128` — a second DRM device (a discrete GPU, or a
`simpledrm`/`vkms` node claiming card0) shifts the iGPU's node to
`renderD129`, which used to be unreachable without dropping to the "custom"
preset. `app/hwaccel.py` enumerates what's actually present.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any

DEFAULT_PRESET = "software"
DEFAULT_HWACCEL_DEVICE = "/dev/dri/renderD128"
DEFAULT_FFMPEG_LOGLEVEL = "warning"

# What `ffmpeg_debug` raises the log level to. "verbose" is the lowest level
# that includes hwaccel device init and filter-graph format negotiation —
# the two things that actually explain a VAAPI/QSV failure. "debug" adds
# per-frame spam that drowns them out.
DEBUG_FFMPEG_LOGLEVEL = "verbose"

# ATSC OTA is frequently 1080i (most CBS/NBC affiliates), and ffmpeg's VAAPI
# and QSV H.264 encoders have no interlaced support at all — they either
# refuse the stream or emit combed frames. `deint=interlaced` restricts yadif
# to frames actually flagged interlaced, so 720p59.94 affiliates (ABC/FOX)
# pass through untouched rather than paying for a pointless filter pass.
# `format=nv12,hwupload` is what moves software-decoded frames into GPU
# memory for the hardware encoder; without it the encoder is handed
# system-memory frames it can't take, and the filter graph fails with
# "Impossible to convert between the formats supported by the filter
# 'graph 0 input from stream 0:0' and the filter 'auto_scale_0'".
_HWUPLOAD_VF = "yadif=deint=interlaced,format=nv12,hwupload"


class InvalidCustomFfmpegArgsError(ValueError):
    """A saved `custom_ffmpeg_args` string couldn't be parsed as shell-style
    arguments (e.g. an unbalanced quote) — lets callers turn this into a
    clean 400 instead of a raw `shlex` `ValueError`/crash reaching the user.
    """


@dataclass(frozen=True)
class TranscodePreset:
    label: str
    description: str
    input_args: list[str] = field(default_factory=list)
    output_args: list[str] = field(default_factory=list)
    # Whether this preset depends on a GPU/driver being reachable from the
    # backend process. Drives the extra diagnostics the /stream route runs
    # when one of these fails (app/api/hdhomerun.py) and which presets
    # app/hwaccel.py test-encodes through.
    hardware: bool = False


TRANSCODE_PRESETS: dict[str, TranscodePreset] = {
    "software": TranscodePreset(
        label="Software (libx264)",
        description=(
            "CPU-only encode — works on any machine and is the safe default, "
            "at the cost of real CPU load per concurrent viewer."
        ),
        # -ac 2: ATSC OTA audio is commonly 5.1 (6-channel) AC-3. ffmpeg's aac
        # encoder happily passes the channel count through, but browsers'
        # MSE AAC decoders only reliably support stereo — appending a
        # 6-channel AAC init segment gets silently rejected by the
        # SourceBuffer (a MediaSource-ending error with no ERROR event from
        # the player library), producing a blank video despite a healthy 200
        # response and real bytes flowing. Confirmed against a real
        # HDHomeRun tuner via mpegts.js's SourceBuffer error trace.
        output_args=["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac", "-ac", "2"],
    ),
    "software_lowpower": TranscodePreset(
        label="Software, low-power (for Raspberry Pi / ARM SBCs)",
        description=(
            "Still CPU-only, but tuned for weak ARM boards: ffmpeg has no "
            "reliable hardware H.264 *encoder* for the Raspberry Pi (its GPU "
            "only accelerates decode), so this trades bitrate efficiency for "
            "much less CPU per frame via preset=ultrafast."
        ),
        output_args=[
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-tune",
            "zerolatency",
            "-c:a",
            "aac",
            "-ac",
            "2",
        ],
    ),
    "videotoolbox": TranscodePreset(
        label="Apple VideoToolbox (macOS)",
        description="Hardware encode on macOS — Intel or Apple Silicon — e.g. running the backend on a Mac/MacBook.",
        hardware=True,
        # a53cc (embedding the source's ATSC closed-caption SEI into the
        # output) defaults to on and reliably crashes ffmpeg's VideoToolbox
        # encoder wrapper on OTA streams that carry CEA-608/708 captions —
        # confirmed against a real HDHomeRun tuner: with it left on, ffmpeg
        # runs and audio flows, but zero video frames ever get encoded
        # (silent black/frozen playback despite a 200 response). Disabling
        # it just drops caption passthrough; the picture is unaffected.
        #
        # -profile:v high -level 4.0: without an explicit level, the
        # VideoToolbox wrapper signals Level 3.1 even when actually encoding
        # 720p59.94 content, which needs Level 4.0+ (3.1's macroblock/sec
        # budget doesn't cover 720p at 60fps) — a non-conformant bitstream
        # that browsers can demux fine (so the network tab looks healthy)
        # but silently fail to decode frames from. Forcing 4.0 covers every
        # ATSC OTA resolution/frame-rate combination in practice (up to
        # 1080i/p at 30fps, or 720p at 60fps).
        output_args=[
            "-c:v",
            "h264_videotoolbox",
            "-a53cc",
            "0",
            "-profile:v",
            "high",
            "-level",
            "4.0",
            "-b:v",
            "6M",
            "-c:a",
            "aac",
            "-ac",
            "2",
        ],
    ),
    "qsv": TranscodePreset(
        label="Intel Quick Sync Video",
        description=(
            "Hardware H.264 encode on Intel CPUs with an iGPU, on Linux with "
            "the intel-media-driver installed and the render device readable "
            "by the backend process. Decodes the tuner's MPEG-2 in software "
            "and uploads to the GPU to encode. The Docker image bundles the "
            "driver (see backend/Dockerfile); on Docker Compose you still "
            "need the /dev/dri passthrough in docker-compose.yml. Run the "
            "hardware-acceleration diagnostics if this fails — on newer "
            "Intel parts (Alder Lake-N and later) QSV may be unavailable "
            'even when VAAPI works; prefer "VAAPI" there.'
        ),
        hardware=True,
        # QSV on Linux sits on top of VAAPI. Deriving the QSV device from an
        # explicit VAAPI child device (`qsv=hw@va`) and naming it as the
        # filter device is what makes `hwupload` target the right GPU —
        # `-qsv_device` alone sets up the *decoder's* device and leaves the
        # filter graph with none, so hwupload fails to find a hw context.
        input_args=[
            "-init_hw_device",
            "vaapi=va:{device}",
            "-init_hw_device",
            "qsv=hw@va",
            "-filter_hw_device",
            "hw",
        ],
        output_args=[
            "-vf",
            # extra_hw_frames: QSV's encoder holds more surfaces in flight
            # than the uploader allocates by default, and runs out mid-stream
            # ("No surplus surface among the current pool") without a bigger
            # pool.
            f"{_HWUPLOAD_VF}=extra_hw_frames=64",
            "-c:v",
            "h264_qsv",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-ac",
            "2",
        ],
    ),
    "vaapi": TranscodePreset(
        label="VAAPI (Intel/AMD, Linux)",
        description=(
            "Hardware H.264 encode via VAAPI on Linux — Intel iGPUs or AMD "
            "GPUs with Mesa drivers. Decodes the tuner's MPEG-2 in software "
            "and uploads to the GPU to encode, which is the safe default: "
            "the encode is the expensive half and stays on the GPU, while "
            "not every GPU can still decode MPEG-2 in hardware. The Docker "
            "image bundles the driver (see backend/Dockerfile); on Docker "
            "Compose you still need the /dev/dri passthrough in "
            "docker-compose.yml."
        ),
        hardware=True,
        input_args=["-vaapi_device", "{device}"],
        output_args=["-vf", _HWUPLOAD_VF, "-c:v", "h264_vaapi", "-c:a", "aac", "-ac", "2"],
    ),
    "vaapi_full": TranscodePreset(
        label="VAAPI, full hardware decode + encode (Intel/AMD, Linux)",
        description=(
            'Like "VAAPI", but decodes on the GPU too — lower CPU still, at '
            "the cost of requiring hardware MPEG-2 decode, which newer Intel "
            "GPUs have dropped. If this 502s where the plain VAAPI preset "
            "works, that's the reason: with no hardware MPEG-2 decoder "
            "ffmpeg falls back to software decode, and the encoder then "
            "refuses the system-memory frames it gets handed. The "
            "hardware-acceleration diagnostics report whether "
            "VAProfileMPEG2Main/VAEntrypointVLD is present."
        ),
        hardware=True,
        input_args=["-vaapi_device", "{device}", "-hwaccel", "vaapi", "-hwaccel_output_format", "vaapi"],
        output_args=["-c:v", "h264_vaapi", "-c:a", "aac", "-ac", "2"],
    ),
    "nvenc": TranscodePreset(
        label="NVIDIA NVENC",
        description="Hardware encode on machines with an NVIDIA GPU and current drivers installed.",
        hardware=True,
        input_args=["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"],
        output_args=["-c:v", "h264_nvenc", "-preset", "p4", "-tune", "ll", "-c:a", "aac", "-ac", "2"],
    ),
    "custom": TranscodePreset(
        label="Custom",
        description=(
            "Full manual control — raw ffmpeg arguments, inserted between "
            '"-i <stream>" and the fixed output framing. Falls back to the '
            "Software preset if left blank."
        ),
    ),
}


def resolve_preset(hwaccel: str) -> TranscodePreset:
    return TRANSCODE_PRESETS.get(hwaccel, TRANSCODE_PRESETS[DEFAULT_PRESET])


def resolve_device(settings: dict[str, Any]) -> str:
    """The render node the hwaccel presets' `{device}` placeholder expands to."""
    return (settings.get("hwaccel_device") or "").strip() or DEFAULT_HWACCEL_DEVICE


def resolve_loglevel(settings: dict[str, Any]) -> str:
    return DEBUG_FFMPEG_LOGLEVEL if settings.get("ffmpeg_debug") else DEFAULT_FFMPEG_LOGLEVEL


def _substitute_device(args: list[str], device: str) -> list[str]:
    return [arg.replace("{device}", device) for arg in args]


def _output_args(settings: dict[str, Any]) -> list[str]:
    hwaccel = settings.get("hwaccel", DEFAULT_PRESET)
    if hwaccel == "custom":
        raw = settings.get("custom_ffmpeg_args", "") or ""
        try:
            custom = shlex.split(raw)
        except ValueError as exc:
            raise InvalidCustomFfmpegArgsError(f"Invalid custom ffmpeg arguments: {exc}") from exc
        return custom or TRANSCODE_PRESETS[DEFAULT_PRESET].output_args
    return resolve_preset(hwaccel).output_args


def build_ffmpeg_args(
    settings: dict[str, Any],
    input_url: str,
    *,
    seek_seconds: float | None = None,
    audio_index: int | None = None,
) -> list[str]:
    """Full ffmpeg arg list (excluding the "ffmpeg" program name itself)."""
    preset = resolve_preset(settings.get("hwaccel", DEFAULT_PRESET))
    device = resolve_device(settings)

    input_options = [*_substitute_device(preset.input_args, device)]
    # Pace playback to 1x realtime for DVR recordings (files), which are served
    # as fast as possible over HTTP. Live tuners pace themselves naturally, and
    # so does a tail-follow pipe (app.dvr.builtin.tail_follow) feeding from a
    # capture file that's itself being written in realtime from the tuner.
    if ":5004/auto/v" not in input_url and input_url != "pipe:0":
        input_options.insert(0, "-re")
    if seek_seconds is not None:
        # Input-side -ss (before -i) is demuxer seeking - it jumps to the
        # nearest keyframe before decoding starts, which is what makes
        # "seeking" through a recording playable in real time instead of
        # decoding and discarding everything up to the target.
        input_options[:0] = ["-ss", f"{seek_seconds:.3f}"]

    output_args = _substitute_device(_output_args(settings), device)
    if audio_index is not None:
        # Explicit stream mapping is only needed once we're picking a
        # non-default audio stream (e.g. an ATSC SAP track) - ffmpeg's
        # default stream selection is otherwise left alone.
        output_args = ["-map", "0:v:0", "-map", f"0:a:{audio_index}", *output_args]

    return [
        "-hide_banner",
        "-loglevel",
        resolve_loglevel(settings),
        "-nostats",
        *input_options,
        "-i",
        input_url,
        # Custom args get the same substitution, so "{device}" is usable as a
        # portable stand-in there too rather than forcing a hardcoded path.
        *output_args,
        "-f",
        "mpegts",
        "pipe:1",
    ]


def command_preview(settings: dict[str, Any], stream_placeholder: str = "<channel stream>") -> str:
    """The exact command `/stream` will run, for display in the UI.

    Degrades to an inline error message instead of raising when
    custom_ffmpeg_args is unparseable — this is called unconditionally while
    rendering the widget's summary/detail (see
    HDHomeRunPlugin._settings_view), so raising here would take down the
    whole widget over a typo in a field the user hasn't gotten to fix yet.
    """
    try:
        args = build_ffmpeg_args(settings, stream_placeholder)
    except InvalidCustomFfmpegArgsError as exc:
        return f"<invalid custom ffmpeg arguments: {exc}>"
    return shlex.join(["ffmpeg", *args])
