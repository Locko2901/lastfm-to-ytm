from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ..config import load_custom_playlists
from ..lastfm import fetch_recent_with_diversity
from ..playlist import upsert_playlist
from ..search import resolve_tracks_to_video_ids
from .filter import filter_tracks_by_tags
from .resolver import resolve_tags_for_tracks

if TYPE_CHECKING:
    from ..context import RuntimeContext
    from ..lastfm import Scrobble

log = logging.getLogger(__name__)


def sync_custom_playlists(
    ctx: RuntimeContext,
    recents: list[Scrobble],
    track_to_vid: dict[tuple[str, str], str],
) -> None:
    """Sync all tag-based custom playlists."""
    settings = ctx.settings

    configs = load_custom_playlists(settings.custom_playlists_file)
    if not configs:
        log.debug("No custom playlists configured, skipping")
        return

    log.info("Processing %d custom tag playlist(s)...", len(configs))

    privacy = settings.custom_playlists_privacy_status or settings.privacy_status

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
        log.info("--- Custom playlist: '%s' (tags=%s, match=%s, limit=%s) ---", config.name, list(config.tags), config.match, limit_label)

        wanted_tags = set(config.tags)

        matching_tracks = filter_tracks_by_tags(
            recents,
            tag_map,
            wanted_tags,
            match=config.match,
            min_count=settings.tag_min_count,
            blacklist=config.blacklist,
        )

        video_ids = _resolve_from_existing(matching_tracks, track_to_vid)

        unresolved = [t for t in matching_tracks if (t.artist.lower(), t.track.lower()) not in track_to_vid]
        if unresolved:
            new_ids, _misses, new_mappings, _log = resolve_tracks_to_video_ids(
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

            new_matching = filter_tracks_by_tags(
                new_scrobbles,
                tag_map,
                wanted_tags,
                match=config.match,
                min_count=settings.tag_min_count,
                blacklist=config.blacklist,
            )

            if not new_matching:
                log.info("No new matching tracks found in backfill")
                break

            new_unresolved = [t for t in new_matching if (t.artist.lower(), t.track.lower()) not in track_to_vid]
            if new_unresolved:
                _bf_ids, _misses, bf_mappings, _log = resolve_tracks_to_video_ids(
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

            seen = set(video_ids)
            for t in new_matching:
                key = (t.artist.lower(), t.track.lower())
                vid = track_to_vid.get(key)
                if vid and vid not in seen:
                    video_ids.append(vid)
                    seen.add(vid)

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
            vid = track_to_vid.get(key)
            if vid and vid not in vid_to_track:
                vid_to_track[vid] = (t.artist, t.track)
        log.info("Final playlist for '%s':", config.name)
        for i, vid in enumerate(video_ids, 1):
            artist, track_name = vid_to_track.get(vid, ("?", "?"))
            log.info("  %3d. %s - %s", i, artist, track_name)

        desc = f"Auto-generated tag playlist ({', '.join(config.tags)})"

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
        except Exception as e:
            log.error("Failed to sync custom playlist '%s': %s", config.name, e)
            continue

    ctx.tag_cache.log_metrics("Tag")


def _resolve_from_existing(
    tracks: list,
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
