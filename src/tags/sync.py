from __future__ import annotations

import contextlib
import logging
import os
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..config import load_custom_playlists
from ..lastfm import fetch_recent_with_diversity
from ..playlist import upsert_playlist
from ..playlist.sync import InvalidVideoIDsError, _evict_from_cache
from ..search import resolve_tracks_to_video_ids
from .filter import filter_tracks_by_artists, filter_tracks_by_tags
from .resolver import resolve_tags_for_tracks

if TYPE_CHECKING:
    from ..config import CustomPlaylistConfig, Settings
    from ..context import RuntimeContext
    from ..lastfm import Scrobble
    from ..recency import WeightedTrack

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TagSyncSummary:
    """Aggregate metrics for a tag playlist sync run."""

    tracks_total: int = 0
    tracks_resolved: int = 0
    tracks_missed: int = 0


def sync_custom_playlists(
    ctx: RuntimeContext,
    recents: list[Scrobble],
    track_to_vid: dict[tuple[str, str], str],
) -> TagSyncSummary:
    """Sync all tag-based custom playlists."""
    settings = ctx.settings

    configs = load_custom_playlists(settings.custom_playlists_file)
    if not configs:
        log.debug("No custom playlists configured, skipping")
        return TagSyncSummary()

    trigger = os.environ.get("SYNC_TRIGGER", "cli")
    if trigger == "scheduled":
        skipped = [c.name for c in configs if not c.auto_sync]
        configs = [c for c in configs if c.auto_sync]
        if skipped:
            log.info("Skipping %d playlist(s) excluded from auto-sync: %s", len(skipped), ", ".join(skipped))
        if not configs:
            log.info("No custom playlists enabled for auto-sync")
            return TagSyncSummary()

    log.info("Processing %d custom playlist(s)...", len(configs))

    privacy = settings.custom_playlists_privacy_status or settings.privacy_status
    candidate_keys: set[tuple[str, str]] = set()
    missed_keys: set[tuple[str, str]] = set()

    tag_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
    if any(c.kind == "tags" for c in configs):
        tag_map = resolve_tags_for_tracks(
            recents,
            ctx.tag_cache,
            settings.lastfm_api_key,
            min_count=settings.tag_min_count,
            sleep_between=settings.tag_sleep_between,
            max_retries=settings.lastfm_max_retries,
            tag_overrides=ctx.tag_overrides,
        )

    for config in configs:
        limit_label = "unlimited" if config.limit == 0 else str(config.limit)
        if config.kind == "artists":
            log.info("--- Custom playlist: '%s' (artists=%s, limit=%s) ---", config.name, list(config.artists), limit_label)
        else:
            log.info("--- Custom playlist: '%s' (tags=%s, match=%s, limit=%s) ---", config.name, list(config.tags), config.match, limit_label)

        wanted_tags = set(config.tags)
        wanted_artists = set(config.artists)

        matching_tracks = _filter_for_config(config, recents, tag_map, wanted_tags, wanted_artists, settings)
        candidate_keys.update((t.artist.lower(), t.track.lower()) for t in matching_tracks)

        video_ids = _resolve_from_existing(matching_tracks, track_to_vid)

        unresolved = [t for t in matching_tracks if (t.artist.lower(), t.track.lower()) not in track_to_vid]
        if unresolved:
            new_ids, _misses, new_mappings, run_log = resolve_tracks_to_video_ids(
                ctx.ytm_search,
                unresolved,
                settings.sleep_between_searches,
                settings.early_termination_score,
                ctx.search_cache,
                ctx.search_overrides,
                settings.api_max_retries,
                settings.search_max_workers,
            )
            seen = set(video_ids)
            for vid in new_ids:
                if vid not in seen:
                    video_ids.append(vid)
                    seen.add(vid)
            track_to_vid.update(new_mappings)
            missed_keys.update(
                (entry["artist"].lower(), entry["title"].lower())
                for entry in run_log
                if entry.get("source") in {"blacklisted", "not_found", "not_found_cached"}
            )

        all_recents = list(recents)
        current_pass = 0
        max_backfill = settings.backfill_passes if config.backfill else 0

        effective_limit = config.limit if config.limit > 0 else float("inf")

        while len(video_ids) < effective_limit and current_pass < max_backfill:
            current_pass += 1
            shortage = int(min(effective_limit - len(video_ids), 500))
            log.info(
                "Tag backfill %d: %d/%s tracks for '%s', fetching more...",
                current_pass,
                len(video_ids),
                limit_label,
                config.name,
            )

            # Multiplier of 3 (vs 2 in main backfill) because tag filtering
            # typically discards the majority of fetched scrobbles.
            additional_limit = len(all_recents) + shortage * 3
            more_recents = fetch_recent_with_diversity(
                settings.lastfm_user,
                settings.lastfm_api_key,
                additional_limit,
                max_raw_limit=settings.max_raw_scrobbles + shortage * 3,
                max_retries=settings.lastfm_max_retries,
                max_consecutive_empty=settings.lastfm_max_consecutive_empty,
            )

            new_scrobbles = more_recents[len(all_recents) :]
            if not new_scrobbles:
                log.info("No more scrobbles available for backfill")
                break

            all_recents = more_recents

            if config.kind == "tags":
                new_tag_map = resolve_tags_for_tracks(
                    new_scrobbles,
                    ctx.tag_cache,
                    settings.lastfm_api_key,
                    min_count=settings.tag_min_count,
                    sleep_between=settings.tag_sleep_between,
                    max_retries=settings.lastfm_max_retries,
                    tag_overrides=ctx.tag_overrides,
                )
                tag_map.update(new_tag_map)

            new_matching = _filter_for_config(config, new_scrobbles, tag_map, wanted_tags, wanted_artists, settings)
            candidate_keys.update((t.artist.lower(), t.track.lower()) for t in new_matching)

            if not new_matching:
                log.info("No new matching tracks found in backfill")
                break

            new_unresolved = [t for t in new_matching if (t.artist.lower(), t.track.lower()) not in track_to_vid]
            if new_unresolved:
                _bf_ids, _misses, bf_mappings, run_log = resolve_tracks_to_video_ids(
                    ctx.ytm_search,
                    new_unresolved,
                    settings.sleep_between_searches,
                    settings.early_termination_score,
                    ctx.search_cache,
                    ctx.search_overrides,
                    settings.api_max_retries,
                    settings.search_max_workers,
                )
                track_to_vid.update(bf_mappings)
                missed_keys.update(
                    (entry["artist"].lower(), entry["title"].lower())
                    for entry in run_log
                    if entry.get("source") in {"blacklisted", "not_found", "not_found_cached"}
                )

            seen = set(video_ids)
            for t in new_matching:
                key = (t.artist.lower(), t.track.lower())
                mapped_vid = track_to_vid.get(key)
                if mapped_vid and mapped_vid not in seen:
                    video_ids.append(mapped_vid)
                    seen.add(mapped_vid)

        if config.limit > 0 and len(video_ids) > config.limit:
            video_ids = video_ids[: config.limit]

        if not video_ids:
            log.warning("No tracks matched tags for '%s', skipping", config.name)
            continue

        log.info("Resolved %d tracks for '%s'", len(video_ids), config.name)
        if config.limit > 0 and len(video_ids) < config.limit:
            log.warning("Only found %d/%d tracks for '%s'", len(video_ids), config.limit, config.name)

        vid_to_track: dict[str, tuple[str, str]] = {}
        for t in all_recents:
            key = (t.artist.lower(), t.track.lower())
            mapped_vid = track_to_vid.get(key)
            if mapped_vid and mapped_vid not in vid_to_track:
                vid_to_track[mapped_vid] = (t.artist, t.track)
        log.info("Final playlist for '%s':", config.name)
        for i, vid in enumerate(video_ids, 1):
            artist, track_name = vid_to_track.get(vid, ("?", "?"))
            log.info("  %3d. %s - %s", i, artist, track_name)

        if config.kind == "artists":
            default_desc = f"Auto-generated artist playlist ({', '.join(config.artists)})"
        else:
            default_desc = f"Auto-generated tag playlist ({', '.join(config.tags)})"
        desc = config.description or default_desc
        try:
            upsert_playlist(
                ctx.ytm,
                ctx.playlist_cache,
                config.name,
                desc,
                privacy,
                video_ids,
                max_retries=settings.api_max_retries,
            )
            _record_custom_playlist_sync(settings, config.name, len(video_ids), config.limit)
        except InvalidVideoIDsError as e:
            _evict_from_cache(ctx.search_cache, e.invalid_ids)
            log.info(
                "Re-resolving tracks for '%s' after evicting %d invalid video IDs...",
                config.name,
                len(e.invalid_ids),
            )
            invalid_set = set(e.invalid_ids)
            video_ids = [v for v in video_ids if v not in invalid_set]
            unresolved_again = [
                t
                for t in matching_tracks
                if (t.artist.lower(), t.track.lower()) not in track_to_vid or track_to_vid.get((t.artist.lower(), t.track.lower())) in invalid_set
            ]
            if unresolved_again:
                new_ids, _m, new_map, _rl = resolve_tracks_to_video_ids(
                    ctx.ytm_search,
                    unresolved_again,
                    settings.sleep_between_searches,
                    settings.early_termination_score,
                    ctx.search_cache,
                    ctx.search_overrides,
                    settings.api_max_retries,
                    settings.search_max_workers,
                )
                track_to_vid.update(new_map)
                seen = set(video_ids)
                for vid in new_ids:
                    if vid not in seen:
                        video_ids.append(vid)
                        seen.add(vid)
            try:
                upsert_playlist(
                    ctx.ytm,
                    ctx.playlist_cache,
                    config.name,
                    desc,
                    privacy,
                    video_ids,
                    max_retries=settings.api_max_retries,
                )
                _record_custom_playlist_sync(settings, config.name, len(video_ids), config.limit)
            except Exception as retry_err:
                log.exception("Failed to sync custom playlist '%s' after re-resolve: %s", config.name, retry_err)
                _save_tag_failure(settings, config.name, retry_err)
                _record_custom_playlist_sync(settings, config.name, len(video_ids), config.limit, error=str(retry_err))
                continue
        except Exception as e:
            log.exception("Failed to sync custom playlist '%s': %s", config.name, e)
            _save_tag_failure(settings, config.name, e)
            _record_custom_playlist_sync(settings, config.name, len(video_ids), config.limit, error=str(e))
            continue

    ctx.tag_cache.log_metrics("Tag")

    resolved_keys = {key for key in candidate_keys if key in track_to_vid}
    return TagSyncSummary(
        tracks_total=len(candidate_keys),
        tracks_resolved=len(resolved_keys),
        tracks_missed=len(missed_keys),
    )


def _filter_for_config(
    config: CustomPlaylistConfig,
    tracks: list[Scrobble],
    tag_map: dict[tuple[str, str], list[dict[str, Any]]],
    wanted_tags: set[str],
    wanted_artists: set[str],
    settings: Settings,
) -> list[Scrobble | WeightedTrack]:
    """Filter tracks for a config by either artist or tag criteria."""
    if config.kind == "artists":
        return filter_tracks_by_artists(
            tracks,
            wanted_artists,
            blacklist=config.blacklist,
            blacklist_artists=config.blacklist_artists,
        )
    return filter_tracks_by_tags(
        tracks,
        tag_map,
        wanted_tags,
        match=config.match,
        min_count=settings.tag_min_count,
        blacklist=config.blacklist,
        blacklist_artists=config.blacklist_artists,
    )


def _resolve_from_existing(
    tracks: list[Scrobble | WeightedTrack],
    track_to_vid: dict[tuple[str, str], str],
) -> list[str]:
    """Resolve tracks using existing video ID mappings."""
    video_ids: list[str] = []
    seen: set[str] = set()

    for t in tracks:
        key = (t.artist.lower(), t.track.lower())
        vid = track_to_vid.get(key)
        if vid and vid not in seen:
            video_ids.append(vid)
            seen.add(vid)

    return video_ids


def _save_tag_failure(
    settings: Settings,
    playlist_name: str,
    error: Exception,
) -> None:
    """Save a failure log and fire webhook for a custom playlist error."""
    from ..config import CACHE_DIR
    from ..webhook import send_webhook

    error_message = f"Custom playlist '{playlist_name}': {error}"
    tb_str = traceback.format_exc()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    log_file = CACHE_DIR / ".last_failure.json"

    import json
    from datetime import UTC, datetime

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
        "traceback": tb_str,
        "hint": hint,
        "sync_type": "tags",
        "playlist_name": playlist_name,
    }
    try:
        with log_file.open("w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

    if settings.webhook_url:
        webhook_events = getattr(settings, "webhook_events", "all")
        if webhook_events != "success":
            with contextlib.suppress(Exception):
                send_webhook(
                    settings.webhook_url,
                    status="error",
                    sync_type="tags",
                    error=str(error),
                    allow_private=getattr(settings, "webhook_allow_private", False),
                )


def _record_custom_playlist_sync(
    settings: Settings,
    name: str,
    track_count: int,
    limit: int,
    error: str | None = None,
) -> None:
    """Record a custom playlist sync as a history action (best-effort)."""
    try:
        from ..history import HistoryDB

        if not settings.history_db_enabled:
            return
        db = HistoryDB(settings.history_db_file)
        source = os.environ.get("SYNC_TRIGGER", "cli")
        if error:
            if len(error) > 200:
                error = error[:200] + "\u2026"
            db.record_action(
                "custom_playlist_error",
                detail=f"'{name}' failed: {error}",
                source=source,
            )
        else:
            limit_label = "unlimited" if limit == 0 else str(limit)
            db.record_action(
                "custom_playlist_sync",
                detail=f"'{name}' synced {track_count}/{limit_label} tracks",
                source=source,
            )
    except Exception:
        pass
