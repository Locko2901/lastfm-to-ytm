from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from ..cache.search import NOT_FOUND
from ..recency import WeightedTrack
from .executor import find_on_ytm

if TYPE_CHECKING:
    from ytmusicapi import YTMusic

    from ..lastfm import Scrobble

log = logging.getLogger(__name__)


def resolve_tracks_to_video_ids(
    ytm_search: YTMusic,
    tracks: list[Scrobble | WeightedTrack],
    sleep_between: float,
    early_termination_score: float,
    search_cache,
    search_overrides,
    max_retries: int = 3,
    max_workers: int = 2,
) -> tuple[list[str], int, dict[tuple[str, str], str], list[dict]]:
    """Resolve tracks to video IDs using the three-tier search priority.

    Returns (video_ids, misses, track_to_vid mapping, run_log_mappings).
    """
    track_metadata: list[tuple[str, Scrobble | WeightedTrack]] = []
    track_to_vid: dict[tuple[str, str], str] = {}
    run_log_mappings: list[dict] = []
    misses = 0
    total_tracks = len(tracks)
    seen_vids: set[str] = set()
    unique_count = 0
    duplicate_count = 0
    blacklisted_seen: set[tuple[str, str]] = set()
    not_found_seen: set[tuple[str, str]] = set()

    for t in tracks:
        artist = t.artist
        title = t.track
        album = getattr(t, "album", None)

        if search_overrides.is_blacklisted(artist, title):
            misses += 1
            bl_key = (artist.lower(), title.lower())
            if bl_key not in blacklisted_seen:
                blacklisted_seen.add(bl_key)
                reason = search_overrides.get_blacklist_reason(artist, title)
                reason_str = f" (reason: {reason})" if reason else ""
                log.info("Blacklisted track skipped: %s - %s%s", artist, title, reason_str)
            run_log_mappings.append({"artist": artist, "title": title, "source": "blacklisted"})
            continue

        vid = search_overrides.get(artist, title)
        yt_title = None
        source = "override" if vid else None
        if vid is None:
            cached = search_cache.get(artist, title)
            if cached == NOT_FOUND:
                misses += 1
                nf_key = (artist.lower(), title.lower())
                if nf_key not in not_found_seen:
                    not_found_seen.add(nf_key)
                    log.info("%s [not found, cached]", title)
                run_log_mappings.append({"artist": artist, "title": title, "source": "not_found_cached"})
                continue
            vid = cached
            if vid:
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

                cache_marker = f" [{source}]" if source != "search" else ""
                if isinstance(t, WeightedTrack):
                    log.info(
                        "%d/%d %s (plays=%d, score=%.3f)%s",
                        unique_count,
                        total_tracks,
                        t.track,
                        t.plays,
                        t.score,
                        cache_marker,
                    )
                else:
                    log.info("%d/%d %s%s", unique_count, total_tracks, t.track, cache_marker)
            else:
                duplicate_count += 1
        else:
            misses += 1
            log.warning("Not found: %s - %s", artist, title)
            run_log_mappings.append({"artist": artist, "title": title, "source": "not_found"})

    if duplicate_count > 0:
        log.info("Skipped %d duplicates", duplicate_count)

    return [vid for vid, _ in track_metadata], misses, track_to_vid, run_log_mappings
