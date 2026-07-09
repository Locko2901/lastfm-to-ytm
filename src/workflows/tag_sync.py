"""Tag-based custom playlist sync workflow."""

import json
import logging
import os
import time
import traceback

from ..config import Settings
from ..observability import (
    clear_failure_log,
    fire_webhook,
    get_history_db,
    record_sync_error,
    save_failure_log,
)
from ..playlist import get_playlist_statistics, log_playlist_statistics
from ..playlist import reset_query_counter as reset_playlist_counter
from ..search import get_search_statistics, log_search_statistics, reset_search_statistics
from ..tags.sync import sync_custom_playlists
from ._common import build_context, fetch_scrobbles, scrobbles_from_local_history

log = logging.getLogger(__name__)


def _read_playlist_filter() -> set[str] | None:
    """Parse the optional CUSTOM_PLAYLIST_FILTER env var (JSON list of names)."""
    raw = os.environ.get("CUSTOM_PLAYLIST_FILTER")
    if not raw:
        return None
    try:
        names = json.loads(raw)
    except (ValueError, TypeError):
        log.warning("Ignoring malformed CUSTOM_PLAYLIST_FILTER value")
        return None
    if not isinstance(names, list):
        return None
    cleaned = {str(n).strip() for n in names if str(n).strip()}
    return cleaned or None


def run_tags(settings: Settings, *, dry_run: bool = False) -> None:
    """Run only the custom tag-based playlist sync.

    When ``dry_run`` is ``True``, playlists are resolved but never written to
    YouTube Music; a per-playlist preview is saved for the dashboard instead.
    """
    _start = time.monotonic()
    ctx = build_context(settings)

    reset_search_statistics()
    reset_playlist_counter()

    if settings.use_local_lastfm_db:
        recents = scrobbles_from_local_history(settings)
        if not recents:
            log.warning("Local Last.fm DB has no tracks after sync. Exiting.")
            return
        log.info("Using %d unique tracks from local Last.fm history for custom playlists", len(recents))
    else:
        recents = fetch_scrobbles(settings)
        if not recents:
            log.warning("No recent scrobbles found. Exiting.")
            return

    log.info("Running custom playlist %s only...", "dry run" if dry_run else "sync")

    only_names = _read_playlist_filter()
    if only_names:
        log.info("Restricting sync to %d requested playlist(s): %s", len(only_names), ", ".join(sorted(only_names)))

    try:
        summary = sync_custom_playlists(ctx, recents, track_to_vid={}, only_names=only_names, dry_run=dry_run)
    except Exception as e:
        log.exception("Custom playlist sync failed: %s", e)
        save_failure_log(f"Custom playlist sync failed: {e}", traceback.format_exc(), sync_type="tags")
        record_sync_error(settings, e)
        fire_webhook(settings, status="error", sync_type="tags", error=str(e), duration_secs=time.monotonic() - _start)
        raise

    clear_failure_log()

    log_search_statistics()
    log_playlist_statistics()

    ctx.search_cache.log_metrics("Search")
    ctx.playlist_cache.log_metrics("Playlist")

    if dry_run:
        log.info("Dry run complete: no playlists were modified")
        return

    tag_override_stats = ctx.tag_overrides.stats()
    if tag_override_stats["total"] > 0:
        log.info(
            "Tag overrides: %d (add: %d, replace: %d)",
            tag_override_stats["total"],
            tag_override_stats["add"],
            tag_override_stats["replace"],
        )

    cache_stats = ctx.search_cache._metrics.get_stats()
    search_stats = get_search_statistics()

    db = get_history_db(settings)
    if db:
        source = os.environ.get("SYNC_TRIGGER", "cli")
        db.record_action(
            "sync_complete",
            detail=f"custom playlist sync resolved={summary.tracks_resolved}, missed={summary.tracks_missed}",
            source=source,
        )

        sync_id_str = os.environ.get("HISTORY_SYNC_ID")
        if sync_id_str:
            playlist_stats = get_playlist_statistics()
            db.finish_sync(
                int(sync_id_str),
                status="success",
                tracks_total=summary.tracks_total,
                tracks_resolved=summary.tracks_resolved,
                tracks_missed=summary.tracks_missed,
                api_searches=search_stats.get("total_queries", 0),
                api_playlist_ops=playlist_stats.get("total_queries", 0),
                cache_hits=cache_stats["hits"],
                cache_misses=cache_stats["misses"],
            )

    fire_webhook(
        settings,
        status="success",
        sync_type="tags",
        tracks_resolved=summary.tracks_resolved,
        tracks_missed=summary.tracks_missed,
        tracks_total=summary.tracks_total,
        duration_secs=time.monotonic() - _start,
        cache_hits=cache_stats["hits"],
        cache_misses=cache_stats["misses"],
        api_searches=search_stats.get("total_queries", 0),
    )
