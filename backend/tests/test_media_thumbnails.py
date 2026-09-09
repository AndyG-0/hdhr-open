from __future__ import annotations

import asyncio

from app.dvr.media import shared, thumbnails


class _FakeProcess:
    def __init__(self, returncode: int = 0):
        self.returncode = returncode
        self.killed = False

    async def communicate(self, input: bytes | None = None):
        return b"", b""

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> None:
        pass


async def test_generate_poster_builds_argv_with_image2_and_caches_result(monkeypatch, tmp_path):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)

    captured_argv: list[list[str]] = []

    async def fake_exec(*argv, **kwargs):
        captured_argv.append(list(argv))
        # Simulate writing jpeg data to the output path
        out_path = argv[-1]
        with open(out_path, "wb") as f:
            f.write(b"JPEGDATA")
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await thumbnails.generate_poster("/path/to/video.ts", "rec1", offset_seconds=10.0)

    assert result is not None
    assert result == tmp_path / "rec1.poster.jpg"
    assert result.read_bytes() == b"JPEGDATA"

    # Verify ffmpeg arguments
    assert len(captured_argv) == 1
    argv = captured_argv[0]
    assert "-f" in argv
    f_idx = argv.index("-f")
    assert argv[f_idx + 1] == "image2"
    assert "-ss" in argv
    assert "10.0" in argv

    # Calling a second time should return cached path without executing ffmpeg again
    result_cached = await thumbnails.generate_poster("/path/to/video.ts", "rec1")
    assert result_cached == result
    assert len(captured_argv) == 1


async def test_generate_poster_falls_back_to_start_on_offset_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)

    captured_argv: list[list[str]] = []

    async def fake_exec(*argv, **kwargs):
        captured_argv.append(list(argv))
        # Fail on first attempt (10s seek), succeed on fallback (0s seek)
        if len(captured_argv) == 1:
            return _FakeProcess(returncode=1)
        out_path = argv[-1]
        with open(out_path, "wb") as f:
            f.write(b"FALLBACK_JPEG")
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await thumbnails.generate_poster("/path/to/short_video.ts", "rec_short", offset_seconds=10.0)

    assert result is not None
    assert result.read_bytes() == b"FALLBACK_JPEG"
    assert len(captured_argv) == 2
    assert "-ss" in captured_argv[1]
    assert captured_argv[1][captured_argv[1].index("-ss") + 1] == "0"


async def test_generate_thumbnail_sprite_builds_argv_with_image2(monkeypatch, tmp_path):
    monkeypatch.setattr(shared, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path)

    captured_argv: list[list[str]] = []

    async def fake_exec(*argv, **kwargs):
        captured_argv.append(list(argv))
        out_path = argv[-1]
        with open(out_path, "wb") as f:
            f.write(b"SPRITEDATA")
        return _FakeProcess(returncode=0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    result = await thumbnails.generate_thumbnail_sprite("/path/to/video.ts", "rec1", duration_seconds=600.0)

    assert result is not None
    jpg_path, vtt_path = result
    assert jpg_path == tmp_path / "rec1.jpg"
    assert vtt_path == tmp_path / "rec1.thumbs.vtt"
    assert jpg_path.read_bytes() == b"SPRITEDATA"
    assert vtt_path.exists()

    assert len(captured_argv) == 1
    argv = captured_argv[0]
    assert "-f" in argv
    f_idx = argv.index("-f")
    assert argv[f_idx + 1] == "image2"
