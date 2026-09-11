from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dvr.builtin import capture as capture_module
from app.dvr.builtin.capture import CapturePipeline, sanitize_filename
from app.integrations import tmdb
from app.storage import db


def test_sanitize_filename():
    assert sanitize_filename("The Office (US) - Special!") == "The_Office_US_Special"
    assert sanitize_filename("Show / with / slashes") == "Show_with_slashes"
    assert sanitize_filename("...odd...name...") == "odd_name"
    assert sanitize_filename("") == "recording"


@pytest.mark.asyncio
async def test_start_capture_fails_when_tuner_unconfigured(tmp_db):
    pipeline = CapturePipeline()
    res = await pipeline.start_capture(
        recording_id="rec1",
        channel_number="4.1",
        channel_name="WNBC",
        title="Late Night",
        start_ts=1000.0,
        end_ts=2000.0,
        settings={},
    )
    assert res is None


@pytest.mark.asyncio
async def test_start_capture_writer_loglevel_follows_ffmpeg_debug_setting(tmp_db, tmp_path, monkeypatch):
    """The writer ffmpeg's -loglevel should track the same ffmpeg_debug
    setting the downstream transcode ffmpeg already honors
    (transcoding.resolve_loglevel) - previously it was hardcoded to
    "warning", so toggling the setting had no effect on live tuning."""
    from app import transcoding

    pipeline = CapturePipeline()
    monkeypatch.setattr(pipeline, "_ensure_recordings_dir", lambda: tmp_path)

    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.read = AsyncMock(return_value=b"")

    spawn_mock = AsyncMock(return_value=mock_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn_mock)
    monkeypatch.setattr(capture_module, "run_in_background", lambda coro: coro.close())

    capture = await pipeline.start_capture(
        recording_id="rec_debug",
        channel_number="4.1",
        channel_name="WNBC",
        title="Late Night",
        start_ts=1000.0,
        end_ts=2000.0,
        settings={"tuner_host": "192.168.1.100", "tuner_port": 80, "ffmpeg_debug": True},
    )
    assert capture is not None

    argv = spawn_mock.await_args.args
    loglevel_index = argv.index("-loglevel")
    assert argv[loglevel_index + 1] == transcoding.DEBUG_FFMPEG_LOGLEVEL


@pytest.mark.asyncio
async def test_start_capture_captures_writer_stderr_instead_of_discarding_it(tmp_db, tmp_path, monkeypatch):
    """The writer ffmpeg's stderr used to be read and thrown away
    (drain_stderr()), leaving no way to see why a tuner-lock failure
    happened. It should now retain a tail, the same way the downstream
    transcode ffmpeg's stderr already does (subprocess_streaming.py)."""
    pipeline = CapturePipeline()
    monkeypatch.setattr(pipeline, "_ensure_recordings_dir", lambda: tmp_path)

    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.read = AsyncMock(side_effect=[b"Connection refused - could not connect to tuner", b""])

    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))
    monkeypatch.setattr(capture_module, "run_in_background", lambda coro: coro.close())

    capture = await pipeline.start_capture(
        recording_id="rec_stderr",
        channel_number="4.1",
        channel_name="WNBC",
        title="Late Night",
        start_ts=1000.0,
        end_ts=2000.0,
        settings={"tuner_host": "192.168.1.100", "tuner_port": 80},
    )
    assert capture is not None
    assert capture.drain_task is not None
    await capture.drain_task

    assert bytes(capture.stderr_tail) == b"Connection refused - could not connect to tuner"
    assert capture.stderr_drain_done.is_set()


@pytest.mark.asyncio
async def test_start_and_stop_capture_lifecycle(tmp_db, tmp_path, monkeypatch):
    pipeline = CapturePipeline()
    monkeypatch.setattr(pipeline, "_ensure_recordings_dir", lambda: tmp_path)

    settings = {"tuner_host": "192.168.1.100", "tuner_port": 80}

    # Mock subprocess
    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.read = AsyncMock(return_value=b"")

    monkeypatch.setattr(
        asyncio,
        "create_subprocess_exec",
        AsyncMock(return_value=mock_proc),
    )

    # Mock media_probe
    fake_probe = {
        "duration_seconds": 60.0,
        "video": {"codec": "h264", "width": 1920, "height": 1080, "fps": 29.97},
        "audio": [{"index": 0, "codec": "ac3", "channels": 6, "language": "eng"}],
        "has_captions": True,
    }
    monkeypatch.setattr("app.media_probe.probe", AsyncMock(return_value=fake_probe))
    # fake_probe has_captions=True triggers the eager caption-generation
    # background task; this test isn't exercising that path (see the
    # dedicated tests below), so just discard the scheduled coroutine
    # instead of letting a real ffmpeg call race against mock_proc.
    monkeypatch.setattr(capture_module, "run_in_background", lambda coro: coro.close())

    capture = await pipeline.start_capture(
        recording_id="rec123",
        channel_number="4.1",
        channel_name="WNBC",
        title="The Evening News",
        start_ts=1000.0,
        end_ts=1060.0,
        settings=settings,
        episode_title="Headlines",
        synopsis="Tonight's top stories.",
        image_url="http://example.com/news.jpg",
        category="News",
    )

    assert capture is not None
    assert capture.recording_id == "rec123"
    assert capture.title == "The Evening News"
    assert capture.file_path.name.startswith("The_Evening_News_1000_rec123")

    # Verify DB recorded as 'recording' with metadata
    rec_db = db.get_recording("rec123")
    assert rec_db is not None
    assert rec_db["status"] == "recording"
    assert rec_db["episode_title"] == "Headlines"
    assert rec_db["synopsis"] == "Tonight's top stories."
    assert rec_db["image_url"] == "http://example.com/news.jpg"
    assert rec_db["category"] == "News"

    # Simulate video file creation on disk
    capture.file_path.write_bytes(b"MPEG-TS data" * 10000)

    # Stop capture
    stats = await pipeline.stop_capture("rec123")
    assert stats is not None
    assert stats["status"] == "completed"
    assert stats["file_size_bytes"] > 10240
    mock_proc.terminate.assert_called_once()

    # Verify DB updated to 'completed' with media probe fields
    rec_db_after = db.get_recording("rec123")
    assert rec_db_after is not None
    assert rec_db_after["status"] == "completed"
    assert rec_db_after["file_size_bytes"] > 10240
    assert rec_db_after["video_codec"] == "h264"
    assert rec_db_after["video_width"] == 1920
    assert rec_db_after["video_height"] == 1080
    assert rec_db_after["audio_codec"] == "ac3"
    assert rec_db_after["audio_channels"] == 6
    assert rec_db_after["has_captions"] == 1


async def _start_stop_capture_no_image(pipeline, tmp_path, monkeypatch, recording_id, **start_kwargs):
    monkeypatch.setattr(pipeline, "_ensure_recordings_dir", lambda: tmp_path)

    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.read = AsyncMock(return_value=b"")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))
    monkeypatch.setattr("app.media_probe.probe", AsyncMock(return_value=None))

    capture = await pipeline.start_capture(
        recording_id=recording_id,
        channel_number="4.1",
        channel_name="WNBC",
        title=start_kwargs.pop("title", "Mystery Show"),
        start_ts=1000.0,
        end_ts=1060.0,
        settings={"tuner_host": "192.168.1.100", "tuner_port": 80},
        **start_kwargs,
    )
    capture.file_path.write_bytes(b"MPEG-TS data" * 10000)
    return await pipeline.stop_capture(recording_id)


@pytest.mark.asyncio
async def test_stop_capture_backfills_poster_from_tmdb_when_missing(tmp_db, tmp_path, monkeypatch):
    pipeline = CapturePipeline()
    scheduled: list = []
    monkeypatch.setattr(capture_module, "run_in_background", lambda coro: scheduled.append(coro))
    search_mock = AsyncMock(return_value="https://image.tmdb.org/t/p/w500/poster.jpg")
    monkeypatch.setattr(tmdb, "search_poster", search_mock)

    stats = await _start_stop_capture_no_image(
        pipeline, tmp_path, monkeypatch, "rec-no-image", season_number=1, episode_number=2
    )
    assert stats["status"] == "completed"

    assert len(scheduled) == 1
    await scheduled[0]

    search_mock.assert_awaited_once_with("Mystery Show", "tv")
    rec = db.get_recording("rec-no-image")
    assert rec["image_url"] == "https://image.tmdb.org/t/p/w500/poster.jpg"


@pytest.mark.asyncio
async def test_stop_capture_backfill_uses_tv_hint_without_season_episode(tmp_db, tmp_path, monkeypatch):
    """Most builtin-DVR recordings (even ordinary TV reruns) lack season/
    episode metadata, so their absence must not be treated as a movie signal
    - that previously caused TV content to be searched against
    /search/movie first and surface the wrong poster."""
    pipeline = CapturePipeline()
    scheduled: list = []
    monkeypatch.setattr(capture_module, "run_in_background", lambda coro: scheduled.append(coro))
    search_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(tmdb, "search_poster", search_mock)

    await _start_stop_capture_no_image(pipeline, tmp_path, monkeypatch, "rec-movie")

    assert len(scheduled) == 1
    await scheduled[0]
    search_mock.assert_awaited_once_with("Mystery Show", "tv")


@pytest.mark.asyncio
async def test_stop_capture_backfill_uses_movie_hint_for_movie_category(tmp_db, tmp_path, monkeypatch):
    pipeline = CapturePipeline()
    scheduled: list = []
    monkeypatch.setattr(capture_module, "run_in_background", lambda coro: scheduled.append(coro))
    search_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(tmdb, "search_poster", search_mock)

    await _start_stop_capture_no_image(pipeline, tmp_path, monkeypatch, "rec-movie-cat", category="Movie")

    assert len(scheduled) == 1
    await scheduled[0]
    search_mock.assert_awaited_once_with("Mystery Show", "movie")


@pytest.mark.asyncio
async def test_stop_capture_skips_tmdb_backfill_when_image_already_set(tmp_db, tmp_path, monkeypatch):
    pipeline = CapturePipeline()
    scheduled: list = []
    monkeypatch.setattr(capture_module, "run_in_background", lambda coro: scheduled.append(coro))
    search_mock = AsyncMock(return_value="https://image.tmdb.org/t/p/w500/should-not-be-used.jpg")
    monkeypatch.setattr(tmdb, "search_poster", search_mock)

    await _start_stop_capture_no_image(
        pipeline, tmp_path, monkeypatch, "rec-has-image", image_url="http://example.com/news.jpg"
    )

    assert scheduled == []
    search_mock.assert_not_called()
    rec = db.get_recording("rec-has-image")
    assert rec["image_url"] == "http://example.com/news.jpg"


@pytest.mark.asyncio
async def test_stop_capture_schedules_eager_caption_generation_when_has_captions(tmp_db, tmp_path, monkeypatch):
    pipeline = CapturePipeline()
    monkeypatch.setattr(pipeline, "_ensure_recordings_dir", lambda: tmp_path)

    mock_proc = MagicMock()
    mock_proc.returncode = None
    mock_proc.terminate = MagicMock()
    mock_proc.wait = AsyncMock(return_value=0)
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.read = AsyncMock(return_value=b"")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))
    monkeypatch.setattr("app.media_probe.probe", AsyncMock(return_value={"has_captions": True}))

    scheduled: list = []
    monkeypatch.setattr(capture_module.jobs, "run_in_background", lambda coro: scheduled.append(coro))
    generate_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(capture_module.captions_static, "generate_captions_vtt", generate_mock)

    capture = await pipeline.start_capture(
        recording_id="rec-captions",
        channel_number="4.1",
        channel_name="WNBC",
        title="Caption Show",
        start_ts=1000.0,
        end_ts=1060.0,
        settings={"tuner_host": "192.168.1.100", "tuner_port": 80},
        image_url="http://example.com/already-has-image.jpg",
    )
    capture.file_path.write_bytes(b"MPEG-TS data" * 10000)

    stats = await pipeline.stop_capture("rec-captions")
    assert stats["status"] == "completed"

    assert len(scheduled) == 1
    await scheduled[0]
    generate_mock.assert_awaited_once_with(str(capture.file_path), "rec-captions")


@pytest.mark.asyncio
async def test_stop_capture_does_not_schedule_caption_generation_when_no_captions(tmp_db, tmp_path, monkeypatch):
    pipeline = CapturePipeline()
    scheduled: list = []
    monkeypatch.setattr(capture_module, "run_in_background", lambda coro: scheduled.append(coro))
    generate_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(capture_module.captions_static, "generate_captions_vtt", generate_mock)

    await _start_stop_capture_no_image(
        pipeline, tmp_path, monkeypatch, "rec-no-captions", image_url="http://example.com/img.jpg"
    )

    assert scheduled == []
    generate_mock.assert_not_called()
