"""Shared workflow primitives: context construction and scrobble fetching."""

import logging

from ytmusicapi import YTMusic

from ..cache.playlist import PlaylistCache
from ..cache.search import SearchCache, SearchOverrides
from ..cache.tags import TagCache, TagOverrides
from ..config import Settings
from ..context import RuntimeContext
from ..lastfm import Scrobble, enable_ipv4_only, fetch_recent_with_diversity
from ..ytm import build_oauth_client

log = logging.getLogger(__name__)


def build_context(settings: Settings) -> RuntimeContext:
    """Build the shared RuntimeContext (auth, caches, overrides)."""
    if settings.lastfm_force_ipv4:
        enable_ipv4_only()

    log.info("Authenticating with YTMusic...")
    ytm = build_oauth_client(settings.ytm_auth_path)
    ytm_search = ytm if not settings.use_anon_search else YTMusic()

    return RuntimeContext(
        settings=settings,
        ytm=ytm,
        ytm_search=ytm_search,
        search_cache=SearchCache(
            settings.cache_search_file,
            settings.cache_search_ttl_days,
            settings.cache_notfound_ttl_days,
        ),
        search_overrides=SearchOverrides(settings.cache_overrides_file),
        playlist_cache=PlaylistCache(settings.cache_playlist_file),
        tag_cache=TagCache(settings.tag_cache_file, settings.tag_cache_ttl_days),
        tag_overrides=TagOverrides(settings.tag_overrides_file),
    )


def fetch_scrobbles(settings: Settings) -> list[Scrobble]:
    """Fetch recent scrobbles."""
    log.info("Fetching scrobbles for '%s'...", settings.lastfm_user)
    return fetch_recent_with_diversity(
        settings.lastfm_user,
        settings.lastfm_api_key,
        settings.limit,
        max_raw_limit=settings.max_raw_scrobbles,
        max_retries=settings.lastfm_max_retries,
        max_consecutive_empty=settings.lastfm_max_consecutive_empty,
    )
