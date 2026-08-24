from __future__ import annotations

import pytest

from app import crypto


@pytest.fixture(autouse=True)
def _isolated_key(tmp_path, monkeypatch):
    monkeypatch.setattr(crypto, "SECRET_KEY_PATH", tmp_path / "secret.key")
    crypto.reset_key_cache()
    yield
    crypto.reset_key_cache()


def test_encrypt_then_decrypt_round_trips():
    ciphertext = crypto.encrypt("sk-super-secret")

    assert crypto.decrypt(ciphertext) == "sk-super-secret"


def test_encrypt_output_does_not_contain_the_plaintext():
    ciphertext = crypto.encrypt("sk-super-secret")

    assert "sk-super-secret" not in ciphertext


def test_decrypt_passes_through_legacy_plaintext_unchanged():
    plaintext = "sk-plaintext-from-before-encryption-existed"
    assert crypto.decrypt(plaintext) == plaintext


def test_generates_and_persists_a_key_file_on_first_use():
    assert not crypto.SECRET_KEY_PATH.exists()

    crypto.encrypt("value")

    assert crypto.SECRET_KEY_PATH.exists()
    assert crypto.SECRET_KEY_PATH.read_bytes()


def test_reuses_the_persisted_key_across_separate_encrypt_calls():
    first = crypto.encrypt("value")
    crypto.reset_key_cache()  # force a re-read from disk, not just the in-process cache

    assert crypto.decrypt(first) == "value"


def test_decrypt_returns_empty_string_for_ciphertext_from_a_different_key(tmp_path):
    ciphertext = crypto.encrypt("value")

    crypto.SECRET_KEY_PATH.unlink()
    crypto.reset_key_cache()
    crypto.encrypt("unrelated")  # generates a fresh, different key

    assert crypto.decrypt(ciphertext) == ""
