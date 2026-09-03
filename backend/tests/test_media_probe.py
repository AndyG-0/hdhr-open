from __future__ import annotations

import json

from app import async_utils, media_probe


class _FakeProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, input: bytes | None = None):
        return self._stdout, self._stderr

    def kill(self) -> None:
        pass


def _payload(*, closed_captions: int | None = 0) -> dict:
    video_stream = {
        "index": 0,
        "codec_type": "video",
        "codec_name": "mpeg2video",
        "width": 1280,
        "height": 720,
        "avg_frame_rate": "60000/1001",
    }
    if closed_captions is not None:
        video_stream["closed_captions"] = closed_captions
    return {
        "format": {"duration": "1771.49"},
        "streams": [
            video_stream,
            {"index": 1, "codec_type": "audio", "codec_name": "ac3", "channels": 6, "tags": {"language": "eng"}},
        ],
    }


async def test_probe_requests_analyze_frames_so_closed_captions_gets_populated(monkeypatch):
    # closed_captions is only emitted by ffprobe when frame decoding is
    # requested (-analyze_frames) — without it, the field is silently absent
    # from every stream regardless of whether captions are actually present.
    # See media_probe.py's module docstring/comment for the ffprobe.c source
    # reference that drives this.
    captured_argv: list[str] = []

    async def fake_exec(*argv, **kwargs):
        captured_argv.extend(argv)
        return _FakeProcess(stdout=json.dumps(_payload(closed_captions=1)).encode())

    monkeypatch.setattr(async_utils.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_probe.probe("http://dvr.local/recorded/play?id=1")

    assert "-analyze_frames" in captured_argv
    assert captured_argv.index("-read_intervals") + 1 < len(captured_argv)
    assert result is not None
    assert result["has_captions"] is True


async def test_probe_reports_no_captions_when_ffprobe_omits_the_field(monkeypatch):
    async def fake_exec(*argv, **kwargs):
        return _FakeProcess(stdout=json.dumps(_payload(closed_captions=None)).encode())

    monkeypatch.setattr(async_utils.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_probe.probe("url")

    assert result is not None
    assert result["has_captions"] is False


async def test_probe_extracts_duration_video_and_audio(monkeypatch):
    async def fake_exec(*argv, **kwargs):
        return _FakeProcess(stdout=json.dumps(_payload(closed_captions=0)).encode())

    monkeypatch.setattr(async_utils.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_probe.probe("url")

    assert result is not None
    assert result["duration_seconds"] == 1771.49
    assert result["video"] == {"codec": "mpeg2video", "width": 1280, "height": 720, "fps": 59.94}
    assert result["audio"] == [{
        "index": 0,
        "codec": "ac3",
        "channels": 6,
        "language": "eng",
        "title": "English",
        "is_descriptive": False,
        "is_hearing_impaired": False,
        "is_commentary": False,
        "is_default": False,
    }]


async def test_probe_resolves_audio_titles_and_dispositions(monkeypatch):
    payload = {
        "format": {"duration": "100.0"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "ac3",
                "channels": 6,
                "tags": {"language": "eng"},
                "disposition": {"default": 1},
            },
            {
                "index": 2,
                "codec_type": "audio",
                "codec_name": "ac3",
                "channels": 2,
                "tags": {"language": "spa"},
                "disposition": {"visual_impaired": 1, "descriptions": 1},
            },
            {
                "index": 3,
                "codec_type": "audio",
                "codec_name": "ac3",
                "channels": 2,
                "tags": {"language": "spa"},
                "disposition": {},
            },
            {
                "index": 4,
                "codec_type": "audio",
                "codec_name": "aac",
                "channels": 2,
                "tags": {"title": "Director's Commentary"},
                "disposition": {"comment": 1},
            },
        ],
    }

    async def fake_exec(*argv, **kwargs):
        return _FakeProcess(stdout=json.dumps(payload).encode())

    monkeypatch.setattr(async_utils.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_probe.probe("url")
    assert result is not None
    audio = result["audio"]
    assert len(audio) == 4

    assert audio[0]["title"] == "English"
    assert audio[0]["is_default"] is True

    # ATSC descriptive video tagged nominally as 'spa' resolves to "Descriptive Audio"
    assert audio[1]["title"] == "Descriptive Audio"
    assert audio[1]["is_descriptive"] is True

    # Real Spanish track with no visual_impaired disposition resolves to "Spanish"
    assert audio[2]["title"] == "Spanish"
    assert audio[2]["is_descriptive"] is False

    # Explicit title tag takes precedence
    assert audio[3]["title"] == "Director's Commentary"
    assert audio[3]["is_commentary"] is True



async def test_probe_returns_none_on_nonzero_exit(monkeypatch):
    async def fake_exec(*argv, **kwargs):
        return _FakeProcess(stdout=b"", returncode=1)

    monkeypatch.setattr(async_utils.asyncio, "create_subprocess_exec", fake_exec)

    assert await media_probe.probe("url") is None


async def test_probe_returns_none_on_missing_binary(monkeypatch):
    async def fake_exec(*argv, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "ffprobe")

    monkeypatch.setattr(async_utils.asyncio, "create_subprocess_exec", fake_exec)

    assert await media_probe.probe("url") is None


async def test_probe_in_progress_refuses_when_file_too_small(tmp_path, monkeypatch):
    video_file = tmp_path / "growing.ts"
    video_file.write_bytes(b"x" * 100)

    async def fake_exec(*argv, **kwargs):
        raise AssertionError("ffprobe should not run before the size gate is satisfied")

    monkeypatch.setattr(async_utils.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_probe.probe_in_progress(str(video_file), min_bytes=1024)

    assert result is None


async def test_probe_in_progress_returns_none_when_file_missing(monkeypatch):
    async def fake_exec(*argv, **kwargs):
        raise AssertionError("ffprobe should not run when the file doesn't exist")

    monkeypatch.setattr(async_utils.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_probe.probe_in_progress("/no/such/file.ts", min_bytes=1024)

    assert result is None


async def test_probe_in_progress_probes_and_drops_duration_once_enough_data(tmp_path, monkeypatch):
    video_file = tmp_path / "growing.ts"
    video_file.write_bytes(b"x" * 2048)

    async def fake_exec(*argv, **kwargs):
        return _FakeProcess(stdout=json.dumps(_payload(closed_captions=0)).encode())

    monkeypatch.setattr(async_utils.asyncio, "create_subprocess_exec", fake_exec)

    result = await media_probe.probe_in_progress(str(video_file), min_bytes=1024)

    assert result is not None
    assert result["audio"] == [{
        "index": 0,
        "codec": "ac3",
        "channels": 6,
        "language": "eng",
        "title": "English",
        "is_descriptive": False,
        "is_hearing_impaired": False,
        "is_commentary": False,
        "is_default": False,
    }]
