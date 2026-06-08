"""RuntimeContext (shared dependencies)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ytmusicapi import YTMusic

    from .cache.playlist import PlaylistCache
    from .cache.search import SearchCache, SearchOverrides
    from .cache.tags import TagCache, TagOverrides
    from .config import Settings


@dataclass
class RuntimeContext:
    """Runtime context containing all shared dependencies."""

    settings: Settings
    ytm: YTMusic
    ytm_search: YTMusic
    search_cache: SearchCache
    search_overrides: SearchOverrides
    playlist_cache: PlaylistCache
    tag_cache: TagCache
    tag_overrides: TagOverrides
