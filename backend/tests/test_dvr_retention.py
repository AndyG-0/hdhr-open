from __future__ import annotations

from unittest.mock import MagicMock

from app.dvr.builtin import retention
from app.storage import db


def test_delete_local_recording(tmp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(retention, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(retention, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path / "cache")
    (tmp_path / "cache").mkdir(parents=True, exist_ok=True)

    video_file = tmp_path / "show1.ts"
    video_file.write_bytes(b"TS DATA" * 100)
    caption_file = tmp_path / "cache" / "rec1.vtt"
    caption_file.write_text("WEBVTT\n")

    db.create_recording(
        {
            "id": "rec1",
            "title": "Nightly News",
            "channel_id": "4.1",
            "channel_name_snapshot": "WNBC",
            "start_ts": 1000.0,
            "end_ts": 1800.0,
            "file_path": str(video_file),
            "status": "completed",
        }
    )

    assert retention.delete_local_recording_sync("rec1") is True
    assert not video_file.exists()
    assert not caption_file.exists()
    assert db.get_recording("rec1") is None


def test_enforce_rule_retention_max_episodes(tmp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(retention, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(retention, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path / "cache")
    (tmp_path / "cache").mkdir(parents=True, exist_ok=True)

    rule_id = "rule_daily_news"
    db.create_recording_rule(
        {
            "id": rule_id,
            "provider": "builtin",
            "type": "series",
            "title": "Daily News",
            "max_episodes_to_keep": 2,
        }
    )

    # Create 4 completed recordings for Daily News (timestamps 1000, 2000, 3000, 4000)
    for i, ts in enumerate([1000, 2000, 3000, 4000], start=1):
        f = tmp_path / f"news_{ts}.ts"
        f.write_bytes(b"DATA")
        db.create_recording(
            {
                "id": f"rec_{i}",
                "title": "Daily News",
                "channel_id": "4.1",
                "channel_name_snapshot": "WNBC",
                "start_ts": float(ts),
                "end_ts": float(ts + 1800),
                "file_path": str(f),
                "status": "completed",
            }
        )

    deleted = retention.enforce_rule_retention_sync(rule_id, max_episodes=2)
    assert deleted == 2

    # Oldest 2 (rec_1 and rec_2) should be gone, rec_3 and rec_4 remain
    assert db.get_recording("rec_1") is None
    assert db.get_recording("rec_2") is None
    assert db.get_recording("rec_3") is not None
    assert db.get_recording("rec_4") is not None


def test_enforce_disk_space_limit_stops_once_free(tmp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(retention, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(retention, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path / "cache")

    # Enough recordings that the 50% per-pass cap doesn't kick in before
    # free space recovers.
    for i in range(1, 11):
        f = tmp_path / f"rec_{i}.ts"
        f.write_bytes(b"X" * 1000)
        db.create_recording(
            {
                "id": f"r{i}",
                "title": f"Show {i}",
                "channel_id": "4.1",
                "channel_name_snapshot": "WNBC",
                "start_ts": float(i * 1000),
                "end_ts": float(i * 1000 + 1000),
                "file_path": str(f),
                "status": "completed",
            }
        )

    # Mock disk_usage to report low free space first, then enough after deleting 2 files
    def fake_disk_usage(path):
        remaining = len(db.list_recordings())
        if remaining > 8:
            return MagicMock(free=1 * 1024 * 1024 * 1024)
        return MagicMock(free=10 * 1024 * 1024 * 1024)

    import shutil

    monkeypatch.setattr(shutil, "disk_usage", fake_disk_usage)

    pruned = retention.enforce_disk_space_limit_sync(min_free_bytes=5 * 1024 * 1024 * 1024)
    assert pruned == 2
    assert db.get_recording("r1") is None
    assert db.get_recording("r2") is None
    assert db.get_recording("r3") is not None


def test_enforce_disk_space_limit_caps_deletions_per_pass(tmp_db, tmp_path, monkeypatch):
    """A single low-space reading must not be able to wipe the whole library in
    one pass - deletions are capped at _MAX_PRUNE_FRACTION_PER_PASS of the
    library even if free space never recovers within this pass."""
    monkeypatch.setattr(retention, "RECORDINGS_DIR", tmp_path)
    monkeypatch.setattr(retention, "HDHOMERUN_MEDIA_CACHE_DIR", tmp_path / "cache")

    for i in range(1, 4):
        f = tmp_path / f"rec_{i}.ts"
        f.write_bytes(b"X" * 1000)
        db.create_recording(
            {
                "id": f"r{i}",
                "title": f"Show {i}",
                "channel_id": "4.1",
                "channel_name_snapshot": "WNBC",
                "start_ts": float(i * 1000),
                "end_ts": float(i * 1000 + 1000),
                "file_path": str(f),
                "status": "completed",
            }
        )

    import shutil

    # Free space never recovers, no matter how much gets deleted.
    monkeypatch.setattr(shutil, "disk_usage", lambda path: MagicMock(free=1 * 1024 * 1024 * 1024))

    pruned = retention.enforce_disk_space_limit_sync(min_free_bytes=5 * 1024 * 1024 * 1024)

    # With 3 completed recordings and a 50% per-pass cap, only 1 can be
    # deleted this pass - the rest of the library survives even though the
    # disk is still "low" the whole time.
    assert pruned == 1
    assert db.get_recording("r1") is None
    assert db.get_recording("r2") is not None
    assert db.get_recording("r3") is not None
