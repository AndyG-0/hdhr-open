from __future__ import annotations

import pytest

from app import transcoding


def test_build_ffmpeg_args_defaults_to_software_preset():
    args = transcoding.build_ffmpeg_args({}, "http://tuner:5004/auto/v11.7")

    assert args == [
        "-hide_banner",
        "-loglevel",
        "warning",
        "-nostats",
        "-i",
        "http://tuner:5004/auto/v11.7",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-c:a",
        "aac",
        "-ac",
        "2",
        "-f",
        "mpegts",
        "pipe:1",
    ]


def test_build_ffmpeg_args_unknown_hwaccel_falls_back_to_software():
    args = transcoding.build_ffmpeg_args({"hwaccel": "not-a-real-preset"}, "url")

    assert args == transcoding.build_ffmpeg_args({"hwaccel": "software"}, "url")


def test_build_ffmpeg_args_adds_re_for_recorded_streams():
    # If the URL is not a live tuner stream, we insert -re to pace the read rate.
    args = transcoding.build_ffmpeg_args({}, "http://192.168.50.197:50000/recorded/play?id=123")
    assert "-re" in args
    assert args.index("-re") < args.index("-i")

    # If it is a live tuner stream, -re must be omitted.
    args_tuner = transcoding.build_ffmpeg_args({}, "http://192.168.50.33:5004/auto/v11.7")
    assert "-re" not in args_tuner


def test_build_ffmpeg_args_includes_hwaccel_input_args():
    args = transcoding.build_ffmpeg_args({"hwaccel": "vaapi"}, "url")

    assert "-vaapi_device" in args
    assert "/dev/dri/renderD128" in args
    assert "h264_vaapi" in args
    # input args (hwaccel setup) must come before -i, output args after
    assert args.index("-vaapi_device") < args.index("-i")
    assert args.index("h264_vaapi") > args.index("-i")


def test_vaapi_and_qsv_upload_software_decoded_frames_to_the_gpu():
    # Regression test for the 502-on-every-stream failure this fixes: the
    # tuner sends MPEG-2, which newer Intel GPUs cannot hardware-decode, so
    # ffmpeg decodes it in software. Without an explicit hwupload the
    # hardware encoder is then handed system-memory frames and the filter
    # graph dies with "Impossible to convert between the formats supported
    # by the filter 'graph 0 input from stream 0:0' and the filter
    # 'auto_scale_0'" — before a single byte reaches stdout.
    for preset_id in ("vaapi", "qsv"):
        args = transcoding.build_ffmpeg_args({"hwaccel": preset_id}, "url")
        video_filter = args[args.index("-vf") + 1]
        assert "hwupload" in video_filter, preset_id
        assert "format=nv12" in video_filter, preset_id
        # deint=interlaced, not a blanket deinterlace: 720p59.94 affiliates
        # shouldn't pay for a filter pass they don't need.
        assert "yadif=deint=interlaced" in video_filter, preset_id
        # Software decode means *not* asking the decoder for GPU surfaces.
        assert "-hwaccel_output_format" not in args, preset_id


def test_vaapi_full_keeps_full_hardware_decode():
    args = transcoding.build_ffmpeg_args({"hwaccel": "vaapi_full"}, "url")

    assert args[args.index("-hwaccel_output_format") + 1] == "vaapi"
    assert args.index("-hwaccel_output_format") < args.index("-i")
    assert "hwupload" not in " ".join(args)


def test_qsv_derives_its_device_from_a_vaapi_child_device():
    # -qsv_device alone sets up the decoder's device and leaves the filter
    # graph without one, so hwupload can't find a hardware context.
    args = transcoding.build_ffmpeg_args({"hwaccel": "qsv"}, "url")

    assert args[args.index("-filter_hw_device") + 1] == "hw"
    assert "vaapi=va:/dev/dri/renderD128" in args
    assert "qsv=hw@va" in args
    assert args.index("-filter_hw_device") < args.index("-i")


def test_hwaccel_device_setting_substitutes_into_every_preset():
    # The iGPU isn't always renderD128 — a second DRM device shifts it to
    # renderD129, which used to be unreachable without the custom preset.
    for preset_id in ("vaapi", "vaapi_full", "qsv"):
        args = transcoding.build_ffmpeg_args({"hwaccel": preset_id, "hwaccel_device": "/dev/dri/renderD129"}, "url")
        joined = " ".join(args)
        assert "/dev/dri/renderD129" in joined, preset_id
        assert "renderD128" not in joined, preset_id
        assert "{device}" not in joined, preset_id


def test_blank_hwaccel_device_falls_back_to_the_default():
    args = transcoding.build_ffmpeg_args({"hwaccel": "vaapi", "hwaccel_device": "  "}, "url")

    assert args[args.index("-vaapi_device") + 1] == transcoding.DEFAULT_HWACCEL_DEVICE


def test_ffmpeg_debug_raises_the_log_level():
    args = transcoding.build_ffmpeg_args({"ffmpeg_debug": True}, "url")

    assert args[args.index("-loglevel") + 1] == "verbose"


def test_only_gpu_presets_are_marked_hardware():
    hardware = {preset_id for preset_id, preset in transcoding.TRANSCODE_PRESETS.items() if preset.hardware}

    assert hardware == {"videotoolbox", "qsv", "vaapi", "vaapi_full", "nvenc"}


def test_build_ffmpeg_args_custom_uses_raw_args():
    args = transcoding.build_ffmpeg_args(
        {"hwaccel": "custom", "custom_ffmpeg_args": "-c:v h264_v4l2m2m -b:v 4M -c:a aac"}, "url"
    )

    assert "-c:v" in args
    assert "h264_v4l2m2m" in args
    assert "-b:v" in args
    assert "4M" in args


def test_build_ffmpeg_args_custom_blank_falls_back_to_software_output_args():
    args = transcoding.build_ffmpeg_args({"hwaccel": "custom", "custom_ffmpeg_args": ""}, "url")

    assert args == transcoding.build_ffmpeg_args({"hwaccel": "software"}, "url")


def test_build_ffmpeg_args_custom_with_unbalanced_quote_raises():
    with pytest.raises(transcoding.InvalidCustomFfmpegArgsError):
        transcoding.build_ffmpeg_args({"hwaccel": "custom", "custom_ffmpeg_args": '-c:v "libx264'}, "url")


def test_command_preview_degrades_gracefully_for_unparseable_custom_args():
    preview = transcoding.command_preview({"hwaccel": "custom", "custom_ffmpeg_args": '-c:v "libx264'})

    assert "invalid custom ffmpeg arguments" in preview.lower()


def test_command_preview_uses_placeholder_and_ffmpeg_prefix():
    preview = transcoding.command_preview({"hwaccel": "software"})

    assert preview.startswith("ffmpeg ")
    assert "<channel stream>" in preview


def test_all_presets_produce_valid_arg_lists():
    for preset_id in transcoding.TRANSCODE_PRESETS:
        args = transcoding.build_ffmpeg_args({"hwaccel": preset_id}, "url")
        assert "-i" in args
        assert args[-3:] == ["-f", "mpegts", "pipe:1"]


def test_videotoolbox_disables_a53cc():
    # Regression test: ffmpeg's h264_videotoolbox encoder crashes (silently
    # encodes zero video frames, audio-only output) when a53cc is left at
    # its default of on and the source carries ATSC closed-caption SEI data
    # — confirmed against a real HDHomeRun OTA tuner. See the preset's
    # comment in app/transcoding.py for the reproduction.
    args = transcoding.build_ffmpeg_args({"hwaccel": "videotoolbox"}, "url")

    assert args[args.index("-a53cc") + 1] == "0"


def test_videotoolbox_forces_level_4_0():
    # Regression test: without an explicit level, h264_videotoolbox signals
    # Level 3.1 even when actually encoding 720p59.94 content, which needs
    # Level 4.0+ (3.1's macroblock/sec budget doesn't cover 720p60). Browsers
    # can demux the resulting non-conformant bitstream fine but silently fail
    # to decode any frames from it. See the preset's comment in
    # app/transcoding.py for the reproduction.
    args = transcoding.build_ffmpeg_args({"hwaccel": "videotoolbox"}, "url")

    assert args[args.index("-level") + 1] == "4.0"
    assert args[args.index("-profile:v") + 1] == "high"


def test_build_ffmpeg_args_seek_seconds_inserts_ss_before_input():
    args = transcoding.build_ffmpeg_args({}, "http://dvr.local:50000/recorded/play?id=1", seek_seconds=90.5)

    assert args[args.index("-ss") + 1] == "90.500"
    assert args.index("-ss") < args.index("-i")


def test_build_ffmpeg_args_seek_seconds_comes_before_re():
    # -re paces reads for recorded (non-live) sources; -ss must still land
    # ahead of -i regardless, so ffmpeg seeks before it starts pacing reads.
    args = transcoding.build_ffmpeg_args({}, "http://dvr.local:50000/recorded/play?id=1", seek_seconds=5)

    assert args.index("-ss") < args.index("-re") < args.index("-i")


def test_build_ffmpeg_args_without_seek_seconds_omits_ss():
    args = transcoding.build_ffmpeg_args({}, "url")

    assert "-ss" not in args


def test_build_ffmpeg_args_audio_index_maps_explicit_streams():
    args = transcoding.build_ffmpeg_args({}, "url", audio_index=1)

    assert args[args.index("-map") + 1] == "0:v:0"
    assert "0:a:1" in args
    # The explicit maps must come before the rest of the output args.
    assert args.index("-map") < args.index("-c:v")


def test_build_ffmpeg_args_without_audio_index_omits_map():
    args = transcoding.build_ffmpeg_args({}, "url")

    assert "-map" not in args


def test_all_hwaccel_presets_force_stereo_audio():
    # Regression test: ATSC OTA audio is commonly 5.1 (6-channel) AC-3, and
    # ffmpeg's aac encoder passes the channel count through by default.
    # Browsers' MSE AAC decoders only reliably support stereo, so a
    # 6-channel AAC init segment gets silently rejected by the
    # SourceBuffer (MediaSource ends with no ERROR event from the player
    # library) — a blank video despite a healthy 200 response and real
    # bytes flowing. Confirmed against a real HDHomeRun tuner. "custom" is
    # exempt since it's raw user-supplied args.
    for preset_id, preset in transcoding.TRANSCODE_PRESETS.items():
        if preset_id == "custom":
            continue
        assert "-ac" in preset.output_args, preset_id
        assert preset.output_args[preset.output_args.index("-ac") + 1] == "2", preset_id
