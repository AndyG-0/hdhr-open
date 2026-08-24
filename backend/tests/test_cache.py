from __future__ import annotations

from app.storage.cache import TTLCache


def test_get_missing_key_returns_none():
    cache = TTLCache()
    assert cache.get("missing") is None


def test_set_then_get_returns_value():
    cache = TTLCache()
    cache.set("key", {"a": 1}, ttl_seconds=60)
    assert cache.get("key") == {"a": 1}


def test_expired_entry_returns_none_and_is_evicted(monkeypatch):
    cache = TTLCache()
    times = iter([100.0, 200.0])
    monkeypatch.setattr("app.storage.cache.time.monotonic", lambda: next(times))

    cache.set("key", "value", ttl_seconds=10)  # expires_at = 110.0
    assert cache.get("key") is None  # "now" = 200.0, past expiry
    assert "key" not in cache._store


def test_delete_removes_entry():
    cache = TTLCache()
    cache.set("key", "value", ttl_seconds=60)

    cache.delete("key")

    assert cache.get("key") is None


def test_delete_missing_key_is_a_noop():
    cache = TTLCache()
    cache.delete("missing")  # should not raise
