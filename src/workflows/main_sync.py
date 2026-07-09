"""Main playlist sync workflow."""

import logging
import os
import time
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..context import RuntimeContext
from ..lastfm import Scrobble
from ..observability import (
    clear_failure_log,
    describe_sync_error,
    fire_webhook,
    get_history_db,
    record_near_misses_to_history,
    record_sync_error,
    record_tracks_to_history,
    save_dry_run_preview,
    save_failure_log,
    save_run_log,
)
from ..playlist import build_sync_preview, current_tracks_from_playlist, get_playlist_statistics, log_playlist_statistics, sync_playlist
from ..playlist import reset_query_counter as reset_playlist_counter
from ..playlist.sync import InvalidVideoIDsError, _evict_from_cache, _retry_with_backoff
from ..playlist.weekly import compute_weekly_name, update_weekly_playlist
from ..recency import WeightedTrack, collapse_recency_weighted, dedupe_keep_latest, weight_history_tracks
from ..search import (
    get_search_statistics,
    log_search_statistics,
    reset_search_statistics,
    resolve_tracks_to_video_ids,
)
from ..ytm import create_playlist_with_items, get_existing_playlist_by_name, get_or_rename_playlist
from ._common import build_context, fetch_scrobbles, sync_local_history
from .backfill import reorder_after_backfill, run_backfill

log = logging.getLogger(__name__)


@dataclass
class _PlaylistSyncResult:
    """Outcome of updating or creating the main playlist."""

    playlist_id: str
    valid_video_ids: list[str]
    substitutions: dict[str, str]
    misses: int
    run_log_mappings: list[dict[str, Any]]


def _sync_or_create_playlist(
    ctx: RuntimeContext,
    settings: Settings,
    *,
    tracks: Sequence[Scrobble | WeightedTrack],
    valid_video_ids: list[str],
    target_count: int,
    desc: str,
    misses: int,
    run_log_mappings: list[dict[str, Any]],
    start_time: float,
) -> _PlaylistSyncResult:
    """Update the existing main playlist or create it, returning the sync outcome."""
    existing_id = get_or_rename_playlist(ctx.ytm, settings.playlist_name, cache=ctx.playlist_cache, role="main")
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
                ctx.playlist_cache.set_template(settings.playlist_name, existing_id, valid_video_ids, role="main")
            except InvalidVideoIDsError as e:
                _evict_from_cache(ctx.search_cache, e.invalid_ids)
                log.info("Re-resolving tracks after evicting %d invalid video IDs...", len(e.invalid_ids))
                video_ids, misses, _track_to_vid, run_log_mappings = resolve_tracks_to_video_ids(
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
                ctx.playlist_cache.set_template(settings.playlist_name, existing_id, valid_video_ids, role="main")
            except Exception as e:
                summary = describe_sync_error(str(e))
                log.exception("Sync failed: %s", summary)
                save_failure_log(summary, traceback.format_exc())
                record_sync_error(settings, e)
                fire_webhook(
                    settings,
                    status="error",
                    sync_type="main",
                    error=str(e),
                    tracks_resolved=len(valid_video_ids),
                    tracks_missed=misses,
                    duration_secs=time.monotonic() - start_time,
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
                role="main",
            )
            log.info("Created playlist with %d tracks", len(valid_video_ids))
        except Exception as e:
            log.exception("Create failed: %s", e)
            save_failure_log(f"Create failed: {e}", traceback.format_exc())
            record_sync_error(settings, e)
            fire_webhook(settings, status="error", sync_type="main", error=str(e), duration_secs=time.monotonic() - start_time)
            raise

    return _PlaylistSyncResult(
        playlist_id=pl_id,
        valid_video_ids=valid_video_ids,
        substitutions=substitutions,
        misses=misses,
        run_log_mappings=run_log_mappings,
    )


def _fetch_current_tracks(ctx: RuntimeContext, settings: Settings, playlist_id: str | None) -> list[dict[str, Any]]:
    """Read a playlist's current tracks for a dry-run diff (best-effort, no mutation)."""
    if not playlist_id:
        return []
    try:
        playlist = _retry_with_backoff(
            ctx.ytm.get_playlist,
            playlist_id,
            limit=None,
            max_retries=settings.api_max_retries,
            operation="get_playlist",
        )
    except Exception as e:
        log.warning("Dry run: failed to fetch current playlist state: %s", e)
        return []
    return current_tracks_from_playlist(playlist)


def _emit_dry_run_preview(
    ctx: RuntimeContext,
    settings: Settings,
    *,
    valid_video_ids: list[str],
    run_log_mappings: list[dict[str, Any]],
    track_to_vid: dict[tuple[str, str], str],
    misses: int,
) -> None:
    """Compute and persist a read-only preview of what the sync would change."""
    existing_id = get_existing_playlist_by_name(ctx.ytm, settings.playlist_name, cache=ctx.playlist_cache)
    current_tracks = _fetch_current_tracks(ctx, settings, existing_id)

    resolved_details: dict[str, dict[str, Any]] = {}
    for m in run_log_mappings:
        artist = m.get("artist", "")
        title = m.get("title", "")
        vid = track_to_vid.get((artist.lower(), title.lower()))
        if vid:
            resolved_details[vid] = {
                "artist": artist,
                "title": title,
                "score": m.get("score"),
                "plays": m.get("plays"),
                "source": m.get("source", ""),
            }

    previews = [
        build_sync_preview(
            playlist_name=settings.playlist_name,
            playlist_id=existing_id,
            current_tracks=current_tracks,
            desired_video_ids=valid_video_ids,
            resolved_details=resolved_details,
            misses=misses,
        )
    ]

    weekly_name = compute_weekly_name(settings)
    if weekly_name:
        weekly_id = get_existing_playlist_by_name(ctx.ytm, weekly_name, cache=ctx.playlist_cache)
        weekly_current = _fetch_current_tracks(ctx, settings, weekly_id)
        previews.append(
            build_sync_preview(
                playlist_name=weekly_name,
                playlist_id=weekly_id,
                current_tracks=weekly_current,
                desired_video_ids=valid_video_ids,
                resolved_details=resolved_details,
                misses=misses,
            )
        )

    save_dry_run_preview(previews, kind="main")

    for preview in previews:
        summary = preview["summary"]
        log.info(
            "Dry run preview [%s]: +%d added, -%d removed, %d unchanged, reordered=%s (no changes applied)",
            preview["playlist_name"],
            summary["added"],
            summary["removed"],
            summary["unchanged"],
            summary["reordered"],
        )


def run(settings: Settings, *, dry_run: bool = False) -> None:
    """Run the main playlist sync workflow.

    When ``dry_run`` is ``True``, tracks are fetched and resolved as usual but the
    target playlist is never modified; instead a preview of the pending changes is
    written for the web dashboard.
    """
    _start = time.monotonic()
    ctx = build_context(settings)

    reset_search_statistics()
    reset_playlist_counter()

    if settings.use_local_lastfm_db:
        local_db = sync_local_history(settings)
        records = local_db.get_scoring_rows(min_plays=settings.recency_min_plays)
        local_db.close()
        if not records:
            log.warning("Local Last.fm DB has no tracks after sync. Exiting.")
            return
        weighted = weight_history_tracks(
            records,
            half_life_hours=settings.recency_half_life_hours,
            play_weight=settings.recency_play_weight,
            min_plays=settings.recency_min_plays,
            normalization=settings.recency_normalization,
            velocity_weight=settings.recency_velocity_weight,
        )
        candidate_cap = max(settings.limit * (settings.backfill_passes + 1), settings.limit)
        tracks: Sequence[Scrobble | WeightedTrack] = weighted[:candidate_cap]
        recents: list[Scrobble] = []
        log.info(
            "Resolving up to %d candidate tracks from local Last.fm DB (%d unique tracks scored)...",
            len(tracks),
            len(weighted),
        )
    else:
        recents = fetch_scrobbles(settings)
        if not recents:
            log.warning("No recent scrobbles found. Exiting.")
            return

        if settings.use_recency_weighting:
            tracks = collapse_recency_weighted(
                recents,
                half_life_hours=settings.recency_half_life_hours,
                play_weight=settings.recency_play_weight,
                min_plays=settings.recency_min_plays,
                normalization=settings.recency_normalization,
                velocity_weight=settings.recency_velocity_weight,
                session_weighting=settings.recency_session_weighting,
                session_start=settings.recency_session_start,
                session_end=settings.recency_session_end,
                session_timezone=settings.recency_session_timezone,
            )
            log.info(
                "Aggregated to %d unique tracks (half-life=%.1fh). Resolving on YTM...",
                len(tracks),
                settings.recency_half_life_hours,
            )
        else:
            ordered = sorted(recents, key=lambda x: x.ts, reverse=True)
            tracks = dedupe_keep_latest(ordered) if settings.deduplicate else ordered
            log.info(
                "Prepared %d tracks (%s).",
                len(tracks),
                "deduped" if settings.deduplicate else "with repeats",
            )

        log.info("Resolving %d unique tracks on YTM...", len(tracks))

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

    if not settings.use_local_lastfm_db:
        bf = run_backfill(
            ctx,
            settings,
            recents=recents,
            tracks=list(tracks),
            video_ids=video_ids,
            track_to_vid=track_to_vid,
            run_log_mappings=run_log_mappings,
            misses=misses,
        )
        recents = bf.recents
        tracks = bf.tracks
        video_ids = bf.video_ids
        track_to_vid = bf.track_to_vid
        run_log_mappings = bf.run_log_mappings
        misses = bf.misses

        if bf.happened:
            tracks, video_ids, run_log_mappings = reorder_after_backfill(
                settings,
                recents=recents,
                tracks=tracks,
                video_ids=video_ids,
                track_to_vid=track_to_vid,
                run_log_mappings=run_log_mappings,
            )

    target_count = settings.limit
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

    if dry_run:
        _emit_dry_run_preview(
            ctx,
            settings,
            valid_video_ids=valid_video_ids,
            run_log_mappings=run_log_mappings,
            track_to_vid=track_to_vid,
            misses=misses,
        )
        return

    sync_result = _sync_or_create_playlist(
        ctx,
        settings,
        tracks=tracks,
        valid_video_ids=valid_video_ids,
        target_count=target_count,
        desc=desc,
        misses=misses,
        run_log_mappings=run_log_mappings,
        start_time=_start,
    )
    pl_id = sync_result.playlist_id
    valid_video_ids = sync_result.valid_video_ids
    substitutions = sync_result.substitutions
    misses = sync_result.misses
    run_log_mappings = sync_result.run_log_mappings

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

    clear_failure_log()
    save_run_log(run_log_mappings)

    log_search_statistics()
    log_playlist_statistics()

    ctx.search_cache.log_metrics("Search")
    ctx.playlist_cache.log_metrics("Playlist")

    override_stats = ctx.search_overrides.stats()
    if override_stats["total_overrides"] > 0 or override_stats["total_blacklisted"] > 0 or override_stats.get("total_blacklisted_artists", 0) > 0:
        log.info(
            "Overrides: %d, Blacklisted: %d, Blacklisted artists: %d",
            override_stats["total_overrides"],
            override_stats["total_blacklisted"],
            override_stats.get("total_blacklisted_artists", 0),
        )

    cache_stats = ctx.search_cache.get_stats()
    search_stats = get_search_statistics()

    _record_to_history(
        ctx,
        settings,
        run_log_mappings=run_log_mappings,
        valid_video_ids=valid_video_ids,
        misses=misses,
        tracks=tracks,
        substitutions=substitutions,
        cache_stats=cache_stats,
        search_stats=search_stats,
    )

    _fire_completion_events(
        settings,
        playlist_id=pl_id,
        valid_video_ids=valid_video_ids,
        misses=misses,
        tracks=tracks,
        start_time=_start,
        cache_stats=cache_stats,
        search_stats=search_stats,
    )


def _record_to_history(
    ctx: RuntimeContext,
    settings: Settings,
    *,
    run_log_mappings: list[dict[str, Any]],
    valid_video_ids: list[str],
    misses: int,
    tracks: Sequence[Scrobble | WeightedTrack],
    substitutions: dict[str, str],
    cache_stats: dict[str, Any],
    search_stats: dict[str, Any],
) -> None:
    """Persist this run's track resolutions and metrics to the history DB, if enabled."""
    db = get_history_db(settings)
    if not db:
        return

    record_tracks_to_history(db, run_log_mappings, ctx.search_cache)
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

    sync_id = int(sync_id_str) if sync_id_str else None
    record_near_misses_to_history(db, run_log_mappings, ctx.search_cache, settings.limit, sync_id)

    if settings.history_retention_days > 0:
        db.prune_by_age(settings.history_retention_days)
    if settings.history_max_size_mb > 0:
        db.prune_if_oversized(settings.history_max_size_mb)


def _fire_completion_events(
    settings: Settings,
    *,
    playlist_id: str,
    valid_video_ids: list[str],
    misses: int,
    tracks: Sequence[Scrobble | WeightedTrack],
    start_time: float,
    cache_stats: dict[str, Any],
    search_stats: dict[str, Any],
) -> None:
    """Fire the success webhook summarising a completed main sync."""
    fire_webhook(
        settings,
        status="success",
        sync_type="main",
        tracks_resolved=len(valid_video_ids),
        tracks_missed=misses,
        tracks_total=len(tracks),
        duration_secs=time.monotonic() - start_time,
        cache_hits=cache_stats["hits"],
        cache_misses=cache_stats["misses"],
        api_searches=search_stats.get("total_queries", 0),
        playlist_url=f"https://music.youtube.com/playlist?list={playlist_id}",
    )
