from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ytmusicapi import YTMusic

    from .cache.playlist import PlaylistCache
    from .cache.search import SearchCache, SearchOverrides
    from .config import Settings


@dataclass
class RuntimeContext:
    """Runtime context containing all shared dependencies.

    This replaces the singleton pattern, making dependencies explicit
    and enabling easier testing and multiple configurations.
    """

    settings: Settings
    ytm: YTMusic
    ytm_search: YTMusic
    search_cache: SearchCache
    search_overrides: SearchOverrides
    playlist_cache: PlaylistCache
