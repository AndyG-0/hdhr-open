"""A small, hand-picked map of well-known cable/streaming broadcast
networks (ESPN, TNT, ...) to a direct "watch" URL, shown next to the
network name in Settings -> Recording -> "Unresolved broadcast networks"
(see app.api.sports.list_unresolved_networks). Deliberately not exhaustive -
anything not listed here can still get a user-saved custom link via
app.storage.db.save_network_watch_link, which always takes precedence over
the curated default here.
"""

from __future__ import annotations

KNOWN_WATCH_LINKS: dict[str, str] = {
    "ESPN": "https://www.espn.com/watch/",
    "ESPN2": "https://www.espn.com/watch/",
    "ESPNU": "https://www.espn.com/watch/",
    "ESPNEWS": "https://www.espn.com/watch/",
    "SECNETWORK": "https://www.espn.com/watch/",
    "ACCNETWORK": "https://www.espn.com/watch/",
    "FS1": "https://www.foxsports.com/live",
    "FS2": "https://www.foxsports.com/live",
    "TNT": "https://www.tntdrama.com/watch-tnt",
    "TBS": "https://www.tbs.com/watch-tbs",
    "TRUTV": "https://www.trutv.com/watch-trutv",
    "NFLNETWORK": "https://www.nfl.com/network/watch/nfl-network-live",
    "NBATV": "https://www.nba.com/watch/nba-tv",
    "MLBNETWORK": "https://www.mlb.com/live-stream-games",
    "PEACOCK": "https://www.peacocktv.com/",
    "PARAMOUNT+": "https://www.paramountplus.com/",
}


def known_watch_link(network_name: str | None) -> str | None:
    """Returns the curated watch URL for `network_name`, or None if it isn't
    one of the well-known networks above. Matching is case/whitespace
    insensitive since ESPN's free-text broadcast-network strings aren't a
    clean enum."""
    if not network_name:
        return None
    key = network_name.strip().upper().replace(" ", "")
    return KNOWN_WATCH_LINKS.get(key)
