from __future__ import annotations

from app.dvr.builtin.network_watch_links import known_watch_link


def test_known_watch_link_returns_curated_url():
    assert known_watch_link("ESPN") == "https://www.espn.com/watch/"
    assert known_watch_link("TNT") == "https://www.tntdrama.com/watch-tnt"


def test_known_watch_link_is_case_and_whitespace_insensitive():
    assert known_watch_link(" espn ") == "https://www.espn.com/watch/"
    assert known_watch_link("fs1") == "https://www.foxsports.com/live"


def test_known_watch_link_returns_none_for_unknown_or_empty():
    assert known_watch_link("Some Regional Sports Network") is None
    assert known_watch_link("") is None
    assert known_watch_link(None) is None
