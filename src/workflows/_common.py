"""Shared workflow primitives: context construction and scrobble fetching."""

import logging

from ytmusicapi import YTMusic

from ..cache.playlist import PlaylistCache
from ..cache.search import SearchCache, SearchOverrides
from ..cache.tags import TagCache, TagOverrides
from ..config import Settings
from ..context import RuntimeContext
from ..lastfm import (
    LocalScrobbleDB,
    Scrobble,
    enable_ipv4_only,
    fetch_recent_with_diversity,
    iter_all_scrobbles,
)
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


def sync_local_history(settings: Settings) -> LocalScrobbleDB:
    """Ingest Last.fm scrobbles into the local history DB and return it.

    On the first run (empty DB) this crawls the user's *entire* scrobble
    history, which can take a while. Subsequent runs only fetch scrobbles newer
    than the stored watermark.
    """
    db = LocalScrobbleDB(settings.lastfm_local_db_file)
    last_uts = db.get_last_scrobble_uts()
    full = last_uts is None

    if last_uts is None:
        log.warning(
            "Local Last.fm DB is empty: performing a FULL history crawl for '%s'. "
            "This may take a while on first run, and playlist ordering will switch to "
            "lifetime plays + recency (results may differ from recent-tracks mode).",
            settings.lastfm_user,
        )
        from_ts = None
    else:
        log.info("Updating local Last.fm DB for '%s' (incremental from last sync)...", settings.lastfm_user)
        from_ts = last_uts + 1

    total = 0
    for pages, page in enumerate(
        iter_all_scrobbles(
            settings.lastfm_user,
            settings.lastfm_api_key,
            from_timestamp=from_ts,
            max_retries=settings.lastfm_max_retries,
            max_scrobbles=settings.lastfm_local_db_max_scrobbles,
        ),
        start=1,
    ):
        total += db.ingest_scrobbles(page)
        if full and pages % 25 == 0:
            log.info("  ...ingested %d scrobbles so far (%d pages)", total, pages)

    db.mark_synced(full=full)
    log.info(
        "Local Last.fm DB %s: +%d scrobbles ingested (%d unique tracks total)",
        "full crawl complete" if full else "updated",
        total,
        db.get_track_count(),
    )
    return db
