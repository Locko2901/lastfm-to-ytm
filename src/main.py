import json
import logging
import os
import time
import traceback
from datetime import UTC, datetime

from ytmusicapi import YTMusic

from .cache.playlist import PlaylistCache
from .cache.search import SearchCache, SearchOverrides
from .cache.tags import TagCache, TagOverrides
from .config import CACHE_DIR, Settings
from .context import RuntimeContext
from .history import HistoryDB
from .lastfm import Scrobble, enable_ipv4_only, fetch_recent_with_diversity
from .playlist import get_playlist_statistics, log_playlist_statistics, sync_playlist
from .playlist import reset_query_counter as reset_playlist_counter
from .playlist.sync import InvalidVideoIDsError, _evict_from_cache, _retry_with_backoff
from .playlist.weekly import update_weekly_playlist
from .recency import WeightedTrack, collapse_recency_weighted, dedupe_keep_latest
from .search import get_search_statistics, log_search_statistics, reset_search_statistics, resolve_tracks_to_video_ids
from .webhook import send_webhook
from .ytm import build_oauth_client, create_playlist_with_items, get_existing_playlist_by_name

log = logging.getLogger(__name__)


def _get_history_db(settings: Settings) -> HistoryDB | None:
    """Return HistoryDB instance if enabled, else None."""
    if not settings.history_db_enabled:
        return None
    try:
        return HistoryDB(settings.history_db_file)
    except Exception as e:
        log.warning("Failed to open history DB: %s", e)
        return None


def _record_tracks_to_history(db: HistoryDB, run_log_mappings: list[dict], search_cache) -> None:
    """Record all resolved tracks into the history database."""
    for m in run_log_mappings:
        artist = m.get("artist", "")
        title = m.get("title", "")
        source = m.get("source", "search")
        if not artist or not title:
            continue

        is_miss = source in ("not_found", "not_found_cached", "blacklisted")
        video_id = None
        yt_title = None
        if not is_miss:
            entry = search_cache.get_entry(artist, title)
            if entry:
                video_id = entry.get("video_id")
                yt_title = entry.get("yt_title")

        db.record_track(artist, title, video_id, yt_title, source, missed=is_miss)


def _record_sync_error(settings: Settings, error: Exception) -> None:
    """Record a sync error as a history action (best-effort)."""
    try:
        db = _get_history_db(settings)
        if not db:
            return
        source = os.environ.get("SYNC_TRIGGER", "cli")
        error_str = str(error)
        if len(error_str) > 200:
            error_str = error_str[:200] + "…"
        db.record_action("sync_error", detail=error_str, source=source)

        sync_id_str = os.environ.get("HISTORY_SYNC_ID")
        if sync_id_str:
            db.finish_sync(int(sync_id_str), status="error", error_message=error_str)
    except Exception:
        pass


def _fire_webhook(settings: Settings, *, status: str, sync_type: str = "main", **kwargs) -> None:
    """Send webhook if configured and event matches filter."""
    if not settings.webhook_url:
        return
    if status == "success" and settings.webhook_events == "error":
        return
    try:
        send_webhook(settings.webhook_url, status=status, sync_type=sync_type, **kwargs)
    except Exception as e:
        log.debug("Webhook dispatch failed: %s", e)


def _save_run_log(mappings: list[dict]) -> None:
    """Save the run log for the web dashboard."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log_file = CACHE_DIR / ".last_run_log.json"
    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total": len(mappings),
        "mappings": mappings,
    }
    with log_file.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("Saved run log with %d mappings to %s", len(mappings), log_file)


def _save_failure_log(error_message: str, traceback_str: str | None = None, *, sync_type: str = "main") -> None:
    """Save a failure log."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log_file = CACHE_DIR / ".last_failure.json"

    hint = None
    error_lower = error_message.lower()
    if "401" in error_message or "unauthorized" in error_lower:
        hint = "Authentication expired. Try regenerating YouTube Music auth or check your Last.fm API key."
    elif "403" in error_message or "forbidden" in error_lower:
        hint = "Access denied. You may need to regenerate YouTube Music auth, or you've been rate-limited."
    elif "rate limit" in error_lower:
        hint = "Rate limited by YouTube Music. Wait a few minutes before trying again."

    data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "error": error_message,
        "traceback": traceback_str,
        "hint": hint,
        "sync_type": sync_type,
    }
    with log_file.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("Saved failure log to %s", log_file)


def _clear_failure_log() -> None:
    """Clear the failure log."""
    log_file = CACHE_DIR / ".last_failure.json"
    if log_file.exists():
        log_file.unlink()
        log.debug("Cleared failure log")


def _build_context(settings: Settings) -> RuntimeContext:
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


def _fetch_scrobbles(settings: Settings) -> list[Scrobble]:
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


def run(settings: Settings) -> None:
    """Run the main playlist sync workflow."""
    _start = time.monotonic()
    ctx = _build_context(settings)

    reset_search_statistics()
    reset_playlist_counter()

    recents = _fetch_scrobbles(settings)
    if not recents:
        log.warning("No recent scrobbles found. Exiting.")
        return

    if settings.use_recency_weighting:
        tracks: list[WeightedTrack] = collapse_recency_weighted(
            recents,
            half_life_hours=settings.recency_half_life_hours,
            play_weight=settings.recency_play_weight,
            min_plays=settings.recency_min_plays,
        )
        log.info(
            "Aggregated to %d unique tracks (half-life=%.1fh). Resolving on YTM...",
            len(tracks),
            settings.recency_half_life_hours,
        )
    else:
        ordered = sorted(recents, key=lambda x: x.ts, reverse=True)
        tracks = dedupe_keep_latest(ordered) if settings.deduplicate else ordered  # type: ignore[assignment]
        log.info(
            "Prepared %d tracks (%s).",
            len(tracks),
            "deduped" if settings.deduplicate else "with repeats",
        )

    log.info("Resolving %d unique tracks on YTM...", len(tracks))

    seen_track_keys = {(t.artist.lower(), t.track.lower()) for t in tracks}

    video_ids, misses, track_to_vid, run_log_mappings = resolve_tracks_to_video_ids(
        ctx.ytm_search,
        tracks,
        settings.sleep_between_searches,
        settings.early_termination_score,
        ctx.search_cache,
        ctx.search_overrides,
        settings.api_max_retries,
        settings.search_max_workers,
    )

    seen_video_ids = set(video_ids)
    target_count = settings.limit
    current_pass = 1
    backfill_happened = False

    while len(video_ids) < target_count and current_pass <= settings.backfill_passes:
        shortage = target_count - len(video_ids)
        log.info("Backfill %d: %d/%d tracks, fetching more...", current_pass, len(video_ids), target_count)

        additional_limit = len(recents) + shortage * 2
        more_recents: list[Scrobble] = fetch_recent_with_diversity(
            settings.lastfm_user,
            settings.lastfm_api_key,
            additional_limit,
            max_raw_limit=settings.max_raw_scrobbles + shortage * 2,
            max_retries=settings.lastfm_max_retries,
            max_consecutive_empty=settings.lastfm_max_consecutive_empty,
        )

        new_scrobbles = more_recents[len(recents) :]
        if not new_scrobbles:
            log.info("No more scrobbles available")
            break

        recents = more_recents
        backfill_happened = True

        if settings.use_recency_weighting:
            new_scrobble_tracks = collapse_recency_weighted(
                new_scrobbles,
                half_life_hours=settings.recency_half_life_hours,
                play_weight=settings.recency_play_weight,
                min_plays=settings.recency_min_plays,
            )
            new_tracks = [t for t in new_scrobble_tracks if (t.artist.lower(), t.track.lower()) not in seen_track_keys]
        else:
            ordered = sorted(new_scrobbles, key=lambda x: x.ts, reverse=True)
            deduped = dedupe_keep_latest(ordered) if settings.deduplicate else ordered
            new_tracks = [
                t
                for t in deduped  # type: ignore[assignment]
                if (t.artist.lower(), t.track.lower()) not in seen_track_keys
            ]

        if not new_tracks:
            log.info("No new unique tracks found")
            break

        for t in new_tracks:
            seen_track_keys.add((t.artist.lower(), t.track.lower()))

        log.info("Processing %d new tracks...", len(new_tracks))
        tracks.extend(new_tracks)  # type: ignore[arg-type]

        new_video_ids, new_misses, new_track_to_vid, new_run_log = resolve_tracks_to_video_ids(
            ctx.ytm_search,
            new_tracks,
            settings.sleep_between_searches,
            settings.early_termination_score,
            ctx.search_cache,
            ctx.search_overrides,
            settings.api_max_retries,
            settings.search_max_workers,
        )

        unique_new_vids = [vid for vid in new_video_ids if vid not in seen_video_ids]
        video_ids.extend(unique_new_vids)
        seen_video_ids.update(unique_new_vids)
        run_log_mappings.extend(new_run_log)
        for key, vid in new_track_to_vid.items():
            if key not in track_to_vid:
                track_to_vid[key] = vid
        misses += new_misses
        current_pass += 1

    if backfill_happened and settings.use_recency_weighting:
        log.info("Reordering playlist with final scores...")
        final_tracks = collapse_recency_weighted(
            recents,
            half_life_hours=settings.recency_half_life_hours,
            play_weight=settings.recency_play_weight,
            min_plays=settings.recency_min_plays,
        )

        reordered_video_ids = []
        reordered_tracks = []
        for t in final_tracks:
            key = (t.artist.lower(), t.track.lower())
            if key in track_to_vid:
                vid = track_to_vid[key]
                if vid not in reordered_video_ids:
                    reordered_video_ids.append(vid)
                    reordered_tracks.append(t)

        log.info("Reordered: %d tracks", len(reordered_video_ids))
        video_ids = reordered_video_ids
        tracks = reordered_tracks

    elif backfill_happened:
        resolved_tracks = []
        for vid in video_ids:
            for t in tracks:
                key = (t.artist.lower(), t.track.lower())
                if track_to_vid.get(key) == vid:
                    resolved_tracks.append(t)
                    break
        tracks = resolved_tracks

    if backfill_happened:
        log.info("Final playlist order after backfills:")
        for i, t in enumerate(tracks, 1):
            artist = t.artist
            track_name = t.track
            score_info = f" (score: {t.score:.4f})" if hasattr(t, "score") else ""
            log.info("  %3d. %s - %s%s", i, artist, track_name, score_info)

        run_log_by_key = {(m["artist"].lower(), m["title"].lower()): m for m in run_log_mappings}
        reordered_run_log = []
        for t in tracks:
            key = (t.artist.lower(), t.track.lower())
            if key in run_log_by_key:
                reordered_run_log.append(run_log_by_key[key])
        final_keys = {(t.artist.lower(), t.track.lower()) for t in tracks}
        for m in run_log_mappings:
            key = (m["artist"].lower(), m["title"].lower())
            if key not in final_keys:
                reordered_run_log.append(m)
        run_log_mappings = reordered_run_log

    if len(video_ids) < target_count:
        log.warning("Only found %d/%d unique tracks", len(video_ids), target_count)
    else:
        log.info("Found %d unique tracks", len(video_ids))

    if len(video_ids) > target_count:
        video_ids = video_ids[:target_count]

    original_count = len(video_ids)
    video_ids = list(dict.fromkeys(video_ids))
    if len(video_ids) < original_count:
        log.error(
            "BUG: Removed %d duplicate video IDs - deduplication should happen earlier",
            original_count - len(video_ids),
        )

    valid_video_ids = video_ids
    if not valid_video_ids:
        log.warning("No valid video IDs resolved")
        return

    ordering = "recency-weighted" if settings.use_recency_weighting else "most recent first"
    desc = settings.playlist_description or f"Autogenerated from Last.fm for {settings.lastfm_user} ({ordering})"

    existing_id = get_existing_playlist_by_name(ctx.ytm, settings.playlist_name, cache=ctx.playlist_cache)
    template_changed = ctx.playlist_cache.template_changed(settings.playlist_name, valid_video_ids)
    substitutions: dict[str, str] = {}

    if existing_id:
        log.info("Updating playlist '%s'...", settings.playlist_name)
        try:
            _retry_with_backoff(
                ctx.ytm.edit_playlist,
                existing_id,
                title=settings.playlist_name,
                description=desc,
                privacyStatus=settings.privacy_status,
                max_retries=settings.api_max_retries,
                operation="edit_playlist",
            )
        except Exception as e:
            log.warning("Failed to edit playlist metadata: %s", e)
        if template_changed:
            log.info("Syncing playlist...")
            try:
                substitutions = sync_playlist(ctx.ytm, existing_id, valid_video_ids, max_retries=settings.api_max_retries)
                ctx.playlist_cache.set_template(settings.playlist_name, existing_id, valid_video_ids)
            except InvalidVideoIDsError as e:
                _evict_from_cache(ctx.search_cache, e.invalid_ids)
                log.info("Re-resolving tracks after evicting %d invalid video IDs...", len(e.invalid_ids))
                video_ids, misses, track_to_vid, run_log_mappings = resolve_tracks_to_video_ids(
                    ctx.ytm_search,
                    tracks,
                    settings.sleep_between_searches,
                    settings.early_termination_score,
                    ctx.search_cache,
                    ctx.search_overrides,
                    settings.api_max_retries,
                    settings.search_max_workers,
                )
                valid_video_ids = list(dict.fromkeys(video_ids))
                if len(valid_video_ids) > target_count:
                    valid_video_ids = valid_video_ids[:target_count]
                log.info("Retrying sync with %d tracks...", len(valid_video_ids))
                substitutions = sync_playlist(ctx.ytm, existing_id, valid_video_ids, max_retries=settings.api_max_retries)
                ctx.playlist_cache.set_template(settings.playlist_name, existing_id, valid_video_ids)
            except Exception as e:
                error_msg = str(e)
                if "401" in error_msg or "Unauthorized" in error_msg:
                    log.exception("Sync failed: HTTP 401 - authentication expired")
                    _save_failure_log("HTTP 401 - Unauthorized", traceback.format_exc())
                elif "403" in error_msg or "Forbidden" in error_msg:
                    log.exception("Sync failed: HTTP 403 - rate limit or auth expired")
                    _save_failure_log("HTTP 403 - rate limit or auth expired", traceback.format_exc())
                elif "Expecting value" in error_msg:
                    log.exception("Sync failed: Invalid API response (likely rate limited)")
                    _save_failure_log("Invalid API response (likely rate limited)", traceback.format_exc())
                else:
                    log.exception("Sync failed: %s", e)
                    _save_failure_log(str(e), traceback.format_exc())
                _record_sync_error(settings, e)
                _fire_webhook(
                    settings,
                    status="error",
                    sync_type="main",
                    error=str(e),
                    tracks_resolved=len(valid_video_ids),
                    tracks_missed=misses,
                    duration_secs=time.monotonic() - _start,
                )
                raise
        else:
            log.info("Playlist already up to date")
            ctx.playlist_cache.touch(settings.playlist_name)

        pl_id = existing_id
    else:
        log.info("Creating playlist '%s'...", settings.playlist_name)
        try:
            pl_id = create_playlist_with_items(
                ctx.ytm,
                settings.playlist_name,
                desc,
                settings.privacy_status,
                valid_video_ids,
                cache=ctx.playlist_cache,
            )
            log.info("Created playlist with %d tracks", len(valid_video_ids))
        except Exception as e:
            log.exception("Create failed: %s", e)
            _save_failure_log(f"Create failed: {e}", traceback.format_exc())
            _record_sync_error(settings, e)
            _fire_webhook(settings, status="error", sync_type="main", error=str(e), duration_secs=time.monotonic() - _start)
            raise

    weekly_id = update_weekly_playlist(
        ctx.ytm,
        get_existing_playlist_by_name,
        create_playlist_with_items,
        sync_playlist,
        settings=settings,
        valid_video_ids=valid_video_ids,
        base_desc=desc,
        cache=ctx.playlist_cache,
    )

    log.info("Done: https://music.youtube.com/playlist?list=%s", pl_id)
    if weekly_id:
        log.info("Weekly: https://music.youtube.com/playlist?list=%s", weekly_id)
    if misses:
        log.info("%d tracks not found", misses)

    _clear_failure_log()

    _save_run_log(run_log_mappings)

    log_search_statistics()
    log_playlist_statistics()

    ctx.search_cache.log_metrics("Search")
    ctx.playlist_cache.log_metrics("Playlist")

    override_stats = ctx.search_overrides.stats()
    if override_stats["total_overrides"] > 0 or override_stats["total_blacklisted"] > 0:
        log.info("Overrides: %d, Blacklisted: %d", override_stats["total_overrides"], override_stats["total_blacklisted"])

    cache_stats = ctx.search_cache._metrics.get_stats()
    search_stats = get_search_statistics()

    db = _get_history_db(settings)
    if db:
        _record_tracks_to_history(db, run_log_mappings, ctx.search_cache)
        source = os.environ.get("SYNC_TRIGGER", "cli")

        for original_id, replaced_id in substitutions.items():
            db.record_action(
                "substitution",
                video_id=replaced_id,
                detail=f"YTM substituted {original_id} → {replaced_id}",
                source=source,
            )

        db.record_action(
            "sync_complete",
            detail=f"resolved={len(valid_video_ids)}, missed={misses}, cache_hits={cache_stats['hits']}",
            source=source,
        )

        sync_id_str = os.environ.get("HISTORY_SYNC_ID")
        if sync_id_str:
            playlist_stats = get_playlist_statistics()
            override_stats_h = ctx.search_overrides.stats()
            db.finish_sync(
                int(sync_id_str),
                status="success",
                tracks_total=len(tracks),
                tracks_resolved=len(valid_video_ids),
                tracks_missed=misses,
                api_searches=search_stats.get("total_queries", 0),
                api_playlist_ops=playlist_stats.get("total_queries", 0),
                cache_hits=cache_stats["hits"],
                cache_misses=cache_stats["misses"],
                override_hits=override_stats_h.get("total_overrides", 0),
            )

        if settings.history_max_size_mb > 0:
            db.prune_if_oversized(settings.history_max_size_mb)

    _fire_webhook(
        settings,
        status="success",
        sync_type="main",
        tracks_resolved=len(valid_video_ids),
        tracks_missed=misses,
        tracks_total=len(tracks),
        duration_secs=time.monotonic() - _start,
        cache_hits=cache_stats["hits"],
        cache_misses=cache_stats["misses"],
        api_searches=search_stats.get("total_queries", 0),
        playlist_url=f"https://music.youtube.com/playlist?list={pl_id}",
    )


def run_tags(settings: Settings) -> None:
    """Run only the custom tag-based playlist sync."""
    from .tags.sync import sync_custom_playlists

    _start = time.monotonic()
    ctx = _build_context(settings)

    reset_search_statistics()
    reset_playlist_counter()

    recents = _fetch_scrobbles(settings)
    if not recents:
        log.warning("No recent scrobbles found. Exiting.")
        return

    log.info("Running tag-based custom playlist sync only...")

    try:
        summary = sync_custom_playlists(ctx, recents, track_to_vid={})
    except Exception as e:
        log.exception("Custom playlist sync failed: %s", e)
        _save_failure_log(f"Custom playlist sync failed: {e}", traceback.format_exc(), sync_type="tags")
        _record_sync_error(settings, e)
        _fire_webhook(settings, status="error", sync_type="tags", error=str(e), duration_secs=time.monotonic() - _start)
        raise

    _clear_failure_log()

    log_search_statistics()
    log_playlist_statistics()

    ctx.search_cache.log_metrics("Search")
    ctx.playlist_cache.log_metrics("Playlist")

    tag_override_stats = ctx.tag_overrides.stats()
    if tag_override_stats["total"] > 0:
        log.info("Tag overrides: %d (add: %d, replace: %d)", tag_override_stats["total"], tag_override_stats["add"], tag_override_stats["replace"])

    cache_stats = ctx.search_cache._metrics.get_stats()
    search_stats = get_search_statistics()

    db = _get_history_db(settings)
    if db:
        source = os.environ.get("SYNC_TRIGGER", "cli")
        db.record_action(
            "sync_complete",
            detail=f"tag sync resolved={summary.tracks_resolved}, missed={summary.tracks_missed}",
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

    _fire_webhook(
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
