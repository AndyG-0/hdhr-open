from __future__ import annotations

import sqlite3

from app import crypto
from app.storage import db


def test_get_app_settings_returns_empty_dict_when_unset(tmp_db):
    assert db.get_app_settings() == {}


def test_save_then_get_app_settings_round_trips(tmp_db):
    db.save_app_settings({"timezone": "America/Chicago"})

    assert db.get_app_settings() == {"timezone": "America/Chicago"}


def test_save_app_settings_overwrites_prior_value(tmp_db):
    db.save_app_settings({"timezone": "UTC"})
    db.save_app_settings({"timezone": "America/Chicago"})

    assert db.get_app_settings() == {"timezone": "America/Chicago"}


def test_save_app_settings_none_value_clears_key(tmp_db):
    db.save_app_settings({"timezone": "UTC", "other": "x"})
    db.save_app_settings({"timezone": None})

    assert db.get_app_settings() == {"other": "x"}


def test_non_secret_app_settings_are_stored_as_plaintext(tmp_db):
    db.save_app_settings({"timezone": "America/Chicago"})

    with sqlite3.connect(tmp_db) as conn:
        stored = conn.execute("SELECT value FROM app_settings WHERE key = 'timezone'").fetchone()[0]

    assert stored == "America/Chicago"


def test_keys_listed_in_secret_app_settings_keys_are_encrypted_on_disk(tmp_db, monkeypatch):
    # This app currently has no secret app_settings keys (real secrets live
    # in network_integrations instead) — monkeypatch one in to exercise the
    # encryption path itself, which is otherwise dead code under the tuple's
    # real (empty) value.
    monkeypatch.setattr(db, "SECRET_APP_SETTINGS_KEYS", ("api_token",))

    db.save_app_settings({"api_token": "sk-secret"})

    with sqlite3.connect(tmp_db) as conn:
        stored = conn.execute("SELECT value FROM app_settings WHERE key = 'api_token'").fetchone()[0]
    assert stored != "sk-secret"
    assert "sk-secret" not in stored

    assert db.get_app_settings() == {"api_token": "sk-secret"}


def test_get_app_settings_omits_a_key_that_fails_to_decrypt(tmp_db, monkeypatch, tmp_path):
    monkeypatch.setattr(db, "SECRET_APP_SETTINGS_KEYS", ("api_token",))
    db.save_app_settings({"api_token": "sk-secret", "timezone": "UTC"})

    # Simulate a rotated/lost encryption key: the stored ciphertext no longer
    # decrypts with the (now different) key.
    crypto.SECRET_KEY_PATH.unlink()
    monkeypatch.setattr(crypto, "SECRET_KEY_PATH", tmp_path / "rotated-secret.key")
    crypto.reset_key_cache()

    assert db.get_app_settings() == {"timezone": "UTC"}
