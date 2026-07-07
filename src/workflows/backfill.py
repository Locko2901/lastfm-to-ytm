"""Backfill loop: fetch additional scrobbles when resolved tracks fall short of target."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ..config import Settings
from ..context import RuntimeContext
from ..lastfm import Scrobble, fetch_recent_with_diversity
from ..recency import WeightedTrack, collapse_recency_weighted, dedupe_keep_latest
from ..search import resolve_tracks_to_video_ids

log = logging.getLogger(__name__)


@dataclass
class BackfillResult:
    """State returned by `run_backfill` after attempting to top up the playlist."""

    recents: list[Scrobble]
    tracks: list[Scrobble | WeightedTrack]
    video_ids: list[str]
    track_to_vid: dict[tuple[str, str], str]
    run_log_mappings: list[dict[str, Any]]
    misses: int
    happened: bool


def run_backfill(
    ctx: RuntimeContext,
    settings: Settings,
    *,
    recents: list[Scrobble],
    tracks: list[Scrobble | WeightedTrack],
    video_ids: list[str],
    track_to_vid: dict[tuple[str, str], str],
    run_log_mappings: list[dict[str, Any]],
    misses: int,
) -> BackfillResult:
    """Run backfill passes until target tracks are resolved or sources exhausted."""
    target_count = settings.limit
    seen_track_keys = {(t.artist.lower(), t.track.lower()) for t in tracks}
    seen_video_ids = set(video_ids)
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
                normalization=settings.recency_normalization,
                velocity_weight=settings.recency_velocity_weight,
                session_weighting=settings.recency_session_weighting,
                session_start=settings.recency_session_start,
                session_end=settings.recency_session_end,
                session_timezone=settings.recency_session_timezone,
            )
            new_tracks: list[Scrobble | WeightedTrack] = [
                t for t in new_scrobble_tracks if (t.artist.lower(), t.track.lower()) not in seen_track_keys
            ]
        else:
            ordered = sorted(new_scrobbles, key=lambda x: x.ts, reverse=True)
            deduped = dedupe_keep_latest(ordered) if settings.deduplicate else ordered
            new_tracks = [t for t in deduped if (t.artist.lower(), t.track.lower()) not in seen_track_keys]

        if not new_tracks:
            log.info("No new unique tracks found")
            break

        for t in new_tracks:
            seen_track_keys.add((t.artist.lower(), t.track.lower()))

        log.info("Processing %d new tracks...", len(new_tracks))
        tracks.extend(new_tracks)

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

    return BackfillResult(
        recents=recents,
        tracks=tracks,
        video_ids=video_ids,
        track_to_vid=track_to_vid,
        run_log_mappings=run_log_mappings,
        misses=misses,
        happened=backfill_happened,
    )


def reorder_after_backfill(
    settings: Settings,
    *,
    recents: list[Scrobble],
    tracks: Sequence[Scrobble | WeightedTrack],
    video_ids: list[str],
    track_to_vid: dict[tuple[str, str], str],
    run_log_mappings: list[dict[str, Any]],
) -> tuple[list[Scrobble | WeightedTrack], list[str], list[dict[str, Any]]]:
    """Recompute ordering after backfill so the final playlist reflects all scrobbles."""
    result_tracks: list[Scrobble | WeightedTrack]
    if settings.use_recency_weighting:
        log.info("Reordering playlist with final scores...")
        final_tracks = collapse_recency_weighted(
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

        reordered_video_ids: list[str] = []
        reordered_tracks: list[Scrobble | WeightedTrack] = []
        for wt in final_tracks:
            key = (wt.artist.lower(), wt.track.lower())
            if key in track_to_vid:
                vid = track_to_vid[key]
                if vid not in reordered_video_ids:
                    reordered_video_ids.append(vid)
                    reordered_tracks.append(wt)

        log.info("Reordered: %d tracks", len(reordered_video_ids))
        video_ids = reordered_video_ids
        result_tracks = reordered_tracks
    else:
        resolved_tracks: list[Scrobble | WeightedTrack] = []
        for vid in video_ids:
            for t in tracks:
                key = (t.artist.lower(), t.track.lower())
                if track_to_vid.get(key) == vid:
                    resolved_tracks.append(t)
                    break
        result_tracks = resolved_tracks

    log.info("Final playlist order after backfills:")
    for i, t in enumerate(result_tracks, 1):
        score_info = f" (score: {t.score:.4f})" if hasattr(t, "score") else ""
        log.info("  %3d. %s - %s%s", i, t.artist, t.track, score_info)

    run_log_by_key = {(m["artist"].lower(), m["title"].lower()): m for m in run_log_mappings}
    reordered_run_log: list[dict[str, Any]] = []
    for t in result_tracks:
        key = (t.artist.lower(), t.track.lower())
        if key in run_log_by_key:
            reordered_run_log.append(run_log_by_key[key])
    final_keys = {(t.artist.lower(), t.track.lower()) for t in result_tracks}
    for m in run_log_mappings:
        key = (m["artist"].lower(), m["title"].lower())
        if key not in final_keys:
            reordered_run_log.append(m)

    return result_tracks, video_ids, reordered_run_log
