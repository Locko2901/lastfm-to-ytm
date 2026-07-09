"""Last.fm API client and scrobble fetching."""

from .fetch import (
    disable_ipv4_only,
    enable_ipv4_only,
    fetch_artist_top_tracks,
    fetch_recent,
    fetch_recent_with_diversity,
    fetch_similar_artists,
    fetch_similar_tracks,
    fetch_track_tags,
    iter_all_scrobbles,
)
from .local_db import LocalScrobbleDB
from .scrobble import Scrobble

__all__ = [
    "LocalScrobbleDB",
    "Scrobble",
    "disable_ipv4_only",
    "enable_ipv4_only",
    "fetch_artist_top_tracks",
    "fetch_recent",
    "fetch_recent_with_diversity",
    "fetch_similar_artists",
    "fetch_similar_tracks",
    "fetch_track_tags",
    "iter_all_scrobbles",
]
