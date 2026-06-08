"""Last.fm API client and scrobble fetching."""

from .fetch import (
    disable_ipv4_only,
    enable_ipv4_only,
    fetch_recent,
    fetch_recent_with_diversity,
    fetch_track_tags,
)
from .scrobble import Scrobble

__all__ = [
    "Scrobble",
    "disable_ipv4_only",
    "enable_ipv4_only",
    "fetch_recent",
    "fetch_recent_with_diversity",
    "fetch_track_tags",
]
