from __future__ import annotations

from app.dvr.builtin.network_affiliates import is_major_network, normalize_major_network_token


def test_is_major_network_rejects_cable_lookalikes():
    assert is_major_network("NBC") is True
    assert is_major_network("FOX") is True
    assert is_major_network("FOXNEWS") is False
    assert is_major_network("FOXSPORTS1") is False
    assert is_major_network("NBCSN") is False
    assert is_major_network(None) is False
    assert is_major_network("TBS") is False


def test_is_major_network_recognizes_pbs_but_not_pbs_kids():
    assert is_major_network("PBS") is True
    assert is_major_network("PBSKIDS") is False


def test_normalize_major_network_token_strips_suffixes_and_uppercases():
    assert normalize_major_network_token("cbs-DT") == "CBS"
    assert normalize_major_network_token("FOX5HD") == "FOX"
    assert normalize_major_network_token("ESPN") is None
    assert normalize_major_network_token("") is None
    assert normalize_major_network_token(None) is None
