"""YouTube Music search, scoring, and matching."""

from .executor import find_on_ytm
from .metrics import (
    get_search_statistics,
    log_search_statistics,
    reset_search_statistics,
)
from .resolver import resolve_tracks_to_video_ids

__all__ = [
    "find_on_ytm",
    "get_search_statistics",
    "log_search_statistics",
    "reset_search_statistics",
    "resolve_tracks_to_video_ids",
]
