import json
import logging
import time
import traceback
from datetime import UTC, datetime

from ytmusicapi import YTMusic

from .cache.playlist import PlaylistCache
from .cache.search import NOT_FOUND, SearchCache, SearchOverrides
from .config import CACHE_DIR, Settings
from .context import RuntimeContext
from .lastfm import Scrobble, enable_ipv4_only, fetch_recent_with_diversity
from .playlist import log_playlist_statistics, sync_playlist
from .playlist import reset_query_counter as reset_playlist_counter
from .playlist.weekly import update_weekly_playlist
from .recency import WeightedTrack, collapse_recency_weighted, dedupe_keep_latest
from .search import find_on_ytm, log_search_statistics, reset_search_statistics
from .ytm import build_oauth_client, create_playlist_with_items, get_existing_playlist_by_name

log = logging.getLogger(__name__)


def _resolve_tracks_to_video_ids(
    ytm_search: YTMusic,
    tracks: list[Scrobble | WeightedTrack],
    sleep_between: float,
    early_termination_score: float,
    search_cache,
    search_overrides,
    max_retries: int = 3,
    max_workers: int = 2,
) -> tuple[list[str], int, dict[tuple[str, str], str], list[dict]]:
    """Resolve tracks to video IDs, deduplicating by video ID.

    Returns:
        Tuple of (video_ids, misses, track_to_vid, run_log_mappings)
    """
    track_metadata: list[tuple[str, Scrobble | WeightedTrack]] = []
    track_to_vid: dict[tuple[str, str], str] = {}
    run_log_mappings: list[dict] = []
    misses = 0
    total_tracks = len(tracks)
    seen_vids: set[str] = set()
    unique_count = 0

    for index, t in enumerate(tracks, start=1):
        artist = t.artist
        title = t.track
        album = getattr(t, "album", None)

        if search_overrides.is_blacklisted(artist, title):
            misses += 1
            run_log_mappings.append({"artist": artist, "title": title, "source": "blacklisted"})
            continue

        # Priority: overrides -> cache -> YTM search
        vid = search_overrides.get(artist, title)
        yt_title = None
        source = "override" if vid else None
        if vid is None:
            cached = search_cache.get(artist, title)
            if cached == NOT_FOUND:
                # Previously searched and not found - skip without re-searching
                misses += 1
                log.info("%d/%d %s [not found, cached]", index, total_tracks, title)
                run_log_mappings.append({"artist": artist, "title": title, "source": "not_found_cached"})
                continue
            vid = cached
            if vid:
                # Get yt_title from cache entry if available
                cache_entry = search_cache.get_entry(artist, title)
                if cache_entry:
                    yt_title = cache_entry.get("yt_title")
            source = "cache" if vid else None
        if vid is None:
            search_result = find_on_ytm(
                ytm_search,
                artist,
                title,
                album,
                early_termination_score,
                max_workers=max_workers,
                max_retries=max_retries,
            )
            if search_result:
                vid, yt_title = search_result
            else:
                vid, yt_title = None, None
            search_cache.set(artist, title, vid, yt_title)
            time.sleep(max(0.0, sleep_between))
            source = "search"

        if vid:
            is_duplicate = vid in seen_vids
            if not is_duplicate:
                seen_vids.add(vid)
                track_metadata.append((vid, t))
                track_key = (artist.lower(), title.lower())
                track_to_vid[track_key] = vid
                unique_count += 1
                run_log_mappings.append({"artist": artist, "title": title, "source": source})

            dup_marker = " [DUP]" if is_duplicate else ""
            cache_marker = f" [{source}]" if source != "search" else ""
            if isinstance(t, WeightedTrack):
                log.info(
                    "%d/%d %s (plays=%d, score=%.3f)%s%s",
                    index,
                    total_tracks,
                    t.track,
                    t.plays,
                    t.score,
                    dup_marker,
                    cache_marker,
                )
            else:
                log.info("%d/%d %s%s%s", index, total_tracks, t.track, dup_marker, cache_marker)
        else:
            misses += 1
            log.warning("%d/%d Not found: %s - %s", index, total_tracks, artist, title)
            run_log_mappings.append({"artist": artist, "title": title, "source": "not_found"})

    if (total_tracks - misses) - unique_count > 0:
        log.info("Skipped %d duplicates", (total_tracks - misses) - unique_count)

    return [vid for vid, _ in track_metadata], misses, track_to_vid, run_log_mappings


def _save_run_log(mappings: list[dict]) -> None:
    """Save the run log for the web dashboard.

    Only stores minimal data (artist, title, source) - the web dashboard
    enriches with video_id/yt_title from the search cache.
    """
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


def _save_failure_log(error_message: str, traceback_str: str | None = None) -> None:
    """Save a failure log when sync fails.

    This is preserved across runs until a successful sync clears it.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log_file = CACHE_DIR / ".last_failure.json"

    # Generate helpful hints based on error type
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
    }
    with log_file.open("w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log.info("Saved failure log to %s", log_file)


def _clear_failure_log() -> None:
    """Clear the failure log on successful sync."""
    log_file = CACHE_DIR / ".last_failure.json"
    if log_file.exists():
        log_file.unlink()
        log.debug("Cleared failure log")


def run(settings: Settings) -> None:
    """Run the main playlist sync workflow."""
    if settings.lastfm_force_ipv4:
        enable_ipv4_only()

    log.info("Authenticating with YTMusic...")
    ytm = build_oauth_client(settings.ytm_auth_path)
    ytm_search = ytm if not settings.use_anon_search else YTMusic()

    # Create context with all dependencies
    ctx = RuntimeContext(
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
    )

    reset_search_statistics()
    reset_playlist_counter()

    log.info("Fetching scrobbles for '%s'...", settings.lastfm_user)
    recents: list[Scrobble] = fetch_recent_with_diversity(
        settings.lastfm_user,
        settings.lastfm_api_key,
        settings.limit,
        max_raw_limit=settings.max_raw_scrobbles,
        max_retries=settings.lastfm_max_retries,
        max_consecutive_empty=settings.lastfm_max_consecutive_empty,
    )
    if not recents:
        log.warning("No recent scrobbles found. Exiting.")
        return

    # Process initial scrobbles into tracks
    if settings.use_recency_weighting:
        tracks: list[WeightedTrack] = collapse_recency_weighted(
            recents,
            half_life_hours=settings.recency_half_life_hours,
            play_weight=settings.recency_play_weight,
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

    video_ids, misses, track_to_vid, run_log_mappings = _resolve_tracks_to_video_ids(
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

        new_video_ids, new_misses, new_track_to_vid, new_run_log = _resolve_tracks_to_video_ids(
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
        # Merge new mappings (don't overwrite existing - keep first resolution)
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

    # Safety dedup check - should never trigger, indicates upstream logic bug
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
    desc = f"Autogenerated from Last.fm for {settings.lastfm_user} ({ordering})"

    existing_id = get_existing_playlist_by_name(ctx.ytm, settings.playlist_name, cache=ctx.playlist_cache)
    template_changed = ctx.playlist_cache.template_changed(settings.playlist_name, valid_video_ids)

    if existing_id:
        log.info("Updating playlist '%s'...", settings.playlist_name)
        try:
            delay = 1.0
            for attempt in range(settings.api_max_retries):
                try:
                    ctx.ytm.edit_playlist(existing_id, title=settings.playlist_name, description=desc, privacyStatus=settings.privacy_status)
                    break
                except Exception as e:
                    if ("403" in str(e) or "Expecting value" in str(e)) and attempt < settings.api_max_retries - 1:
                        time.sleep(delay)
                        delay *= 2
                    elif attempt == settings.api_max_retries - 1:
                        log.debug("Failed to edit playlist metadata: %s", e)
                        break
        except Exception as e:
            log.debug("Unexpected error editing playlist metadata: %s", e)

        if template_changed:
            log.info("Syncing playlist...")
            try:
                sync_playlist(ctx.ytm, existing_id, valid_video_ids, max_retries=settings.api_max_retries)
                ctx.playlist_cache.set_template(settings.playlist_name, existing_id, valid_video_ids)
            except Exception as e:
                error_msg = str(e)
                if "401" in error_msg or "Unauthorized" in error_msg:
                    log.error("Sync failed: HTTP 401 - authentication expired")
                    _save_failure_log("HTTP 401 - Unauthorized", traceback.format_exc())
                elif "403" in error_msg or "Forbidden" in error_msg:
                    log.error("Sync failed: HTTP 403 - rate limit or auth expired")
                    _save_failure_log("HTTP 403 - rate limit or auth expired", traceback.format_exc())
                elif "Expecting value" in error_msg:
                    log.error("Sync failed: Invalid API response (likely rate limited)")
                    _save_failure_log("Invalid API response (likely rate limited)", traceback.format_exc())
                else:
                    log.error("Sync failed: %s", e)
                    _save_failure_log(str(e), traceback.format_exc())
                return
        else:
            log.info("Playlist already up to date")
            ctx.playlist_cache.set_template(settings.playlist_name, existing_id, valid_video_ids)

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
            log.error("Create failed: %s", e)
            _save_failure_log(f"Create failed: {e}", traceback.format_exc())
            return

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

    # Clear failure log on successful sync
    _clear_failure_log()

    # Save run log for web dashboard
    _save_run_log(run_log_mappings)

    log_search_statistics()
    log_playlist_statistics()

    ctx.search_cache.log_metrics("Search")
    ctx.playlist_cache.log_metrics("Playlist")

    override_stats = ctx.search_overrides.stats()
    if override_stats["total_overrides"] > 0 or override_stats["total_blacklisted"] > 0:
        log.info("Overrides: %d, Blacklisted: %d", override_stats["total_overrides"], override_stats["total_blacklisted"])
