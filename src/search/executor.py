from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import TYPE_CHECKING, Any, Literal

from .metrics import (
    increment_early_terminations,
    increment_queries,
    increment_songs_searched,
)
from .queries import build_queries
from .scoring import score_candidate

if TYPE_CHECKING:
    from ytmusicapi import YTMusic

log = logging.getLogger(__name__)

SEARCH_RESULT_LIMIT = 25
YOUTUBE_VIDEO_ID_LENGTH = 11
SEARCH_FILTERS: list[Literal["songs", "videos"] | None] = ["songs", "videos", None]
NUM_SEARCH_FILTERS = len(SEARCH_FILTERS)
BASE_THRESHOLD_NO_ALBUM = 0.66
BASE_THRESHOLD_WITH_ALBUM = 0.68
VIDEO_EXTRA_THRESHOLD = 0.05
BELOW_THRESHOLD_MARGIN = 0.06
INITIAL_RETRY_DELAY = 0.5
RETRY_BACKOFF_FACTOR = 2


def _try_exact_query(
    ytm: YTMusic,
    query: str,
    artist: str,
    title: str,
    album: str | None,
    max_retries: int,
    early_termination_score: float,
) -> tuple[str, str | None, float, int] | None:
    """Try exact query with all three filters. Returns (vid, yt_title, score, query_count) if good match found."""
    filters = SEARCH_FILTERS
    best_vid: str | None = None
    yt_title: str | None = None
    best_score = 0.0
    query_count = 0
    seen: set[str] = set()

    base_threshold = BASE_THRESHOLD_NO_ALBUM if not album else BASE_THRESHOLD_WITH_ALBUM
    video_extra = VIDEO_EXTRA_THRESHOLD
    early_termination_threshold = max(early_termination_score, base_threshold + video_extra)

    for flt in filters:
        delay = INITIAL_RETRY_DELAY
        for attempt in range(max_retries):
            try:
                log.debug("Exact query='%s' with filter='%s'", query, flt or "None")
                results = ytm.search(query, filter=flt, limit=SEARCH_RESULT_LIMIT)
                query_count += 1

                for r in results:
                    rt = (r.get("resultType") or "").lower()
                    if rt not in ("song", "video", ""):
                        continue

                    vid = r.get("videoId")
                    if not (isinstance(vid, str) and len(vid) == YOUTUBE_VIDEO_ID_LENGTH):
                        continue
                    if vid in seen:
                        continue
                    seen.add(vid)

                    score = score_candidate(r, artist, title, album)
                    if score > best_score:
                        best_score = score
                        best_vid = vid
                        yt_title = r.get("title")

                        if score >= early_termination_threshold:
                            log.debug(
                                "Exact query early termination: score %.3f >= %.3f",
                                score,
                                early_termination_threshold,
                            )
                            return (best_vid, yt_title, best_score, query_count)

                break

            except Exception as e:
                error_msg = str(e)
                is_rate_limit = "403" in error_msg or "Forbidden" in error_msg or "Expecting value" in error_msg

                if is_rate_limit and attempt < max_retries - 1:
                    log.debug(
                        "Exact query rate limited (attempt %d/%d), retrying in %.1fs...",
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= RETRY_BACKOFF_FACTOR
                    continue

                log.debug("Exact query failed for filter='%s': %s", flt or "None", error_msg)
                query_count += 1
                break

    if best_vid and best_score >= (base_threshold - BELOW_THRESHOLD_MARGIN):
        return (best_vid, yt_title, best_score, query_count)

    return None


def find_on_ytm(
    ytm: YTMusic,
    artist: str,
    title: str,
    album: str | None = None,
    early_termination_score: float = 0.9,
    max_workers: int = 2,
    max_retries: int = 3,
) -> tuple[str, str | None] | None:
    """Search YouTube Music for a song and return (videoId, yt_title) if match found."""
    increment_songs_searched()

    song_query_count = 0

    log.debug("Searching for: %s - %s%s", artist, title, f" ({album})" if album else "")

    exact_query = f"{artist} - {title}"
    exact_result = _try_exact_query(ytm, exact_query, artist, title, album, max_retries, early_termination_score)
    if exact_result:
        exact_vid, exact_title, score, query_count = exact_result
        song_query_count += query_count
        increment_queries(song_query_count)
        log.debug(
            "Found via exact query: %s (score: %.3f, queries: %d)",
            exact_vid,
            score,
            song_query_count,
        )
        return (exact_vid, exact_title)

    song_query_count += NUM_SEARCH_FILTERS

    already_tried = {exact_query}
    queries = build_queries(artist, title, album, already_tried=already_tried)
    filters = SEARCH_FILTERS

    best_vid: str | None = None
    yt_title: str | None = None
    best_score = 0.0
    best_rt = ""
    seen: set[str] = set()

    base_threshold = BASE_THRESHOLD_NO_ALBUM if not album else BASE_THRESHOLD_WITH_ALBUM
    video_extra = VIDEO_EXTRA_THRESHOLD

    early_termination_enabled = early_termination_score < 1.0
    early_termination_threshold = max(early_termination_score, base_threshold + video_extra)

    def search_with_filter(query_filter_pair: tuple[str, Literal["songs", "videos"] | None]) -> tuple[list[dict[str, Any]], int, str | None]:
        query, flt = query_filter_pair
        delay = INITIAL_RETRY_DELAY

        for attempt in range(max_retries):
            try:
                log.debug("Searching query='%s' with filter='%s'", query, flt or "None")
                results = ytm.search(query, filter=flt, limit=SEARCH_RESULT_LIMIT)
                return results, 1, None
            except Exception as e:
                error_msg = str(e)
                is_rate_limit = "403" in error_msg or "Forbidden" in error_msg or "Expecting value" in error_msg

                if is_rate_limit and attempt < max_retries - 1:
                    log.debug(
                        "Search rate limited (attempt %d/%d), retrying in %.1fs...",
                        attempt + 1,
                        max_retries,
                        delay,
                    )
                    time.sleep(delay)
                    delay *= RETRY_BACKOFF_FACTOR
                    continue

                if "403" in error_msg or "Forbidden" in error_msg:
                    log.error(
                        "Search failed for query '%s' with filter='%s': HTTP 403 Forbidden - Rate limited",
                        query,
                        flt or "None",
                    )
                elif "Expecting value" in error_msg:
                    log.error(
                        "Search failed for query '%s' with filter='%s': Invalid JSON response (possible API error or rate limit)",
                        query,
                        flt or "None",
                    )
                else:
                    log.debug(
                        "Search failed for query '%s' with filter='%s': %s",
                        query,
                        flt or "None",
                        error_msg,
                    )
                return [], 1, error_msg
        return [], 0, "max retries exhausted"

    query_filter_pairs = [(q, flt) for q in queries for flt in filters]

    state_lock = Lock()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_pair = {executor.submit(search_with_filter, pair): pair for pair in query_filter_pairs}

        for future in as_completed(future_to_pair):
            query, flt = future_to_pair[future]

            try:
                results, local_count, error = future.result()
                with state_lock:
                    song_query_count += local_count

                if error:
                    if "Invalid filter" in error:
                        log.warning(
                            "Search failed for query '%s' with filter '%s': %s",
                            query,
                            flt or "None",
                            error,
                        )
                    continue

                if not results:
                    continue

                for r in results:
                    rt = (r.get("resultType") or "").lower()
                    if rt not in ("song", "video", ""):
                        continue

                    vid = r.get("videoId")
                    if not (isinstance(vid, str) and len(vid) == 11):
                        continue

                    with state_lock:
                        if vid in seen:
                            continue
                        seen.add(vid)

                    score = score_candidate(r, artist, title, album)

                    if score > 0.0:
                        log.debug(
                            "Candidate: '%s' by '%s' (score: %.3f, type: %s)",
                            r.get("title"),
                            r.get("author"),
                            score,
                            rt,
                        )

                    with state_lock:
                        if score > best_score:
                            best_score = score
                            best_vid = vid
                            best_rt = rt
                            yt_title = r.get("title")

                    if early_termination_enabled and score >= early_termination_threshold:
                        log.debug(
                            "Early termination: score %.3f >= %.3f",
                            score,
                            early_termination_threshold,
                        )
                        increment_early_terminations()
                        for remaining_future in future_to_pair:
                            if remaining_future != future and not remaining_future.done():
                                remaining_future.cancel()
                        break

                if early_termination_enabled and best_score >= early_termination_threshold:
                    break

            except Exception as e:
                log.debug("Error processing search future: %s", str(e))
                continue

    increment_queries(song_query_count)

    if best_vid:
        log.debug(
            "Found: %s (score: %.3f, queries: %d)",
            best_vid,
            best_score,
            song_query_count,
        )
    else:
        log.warning("No match for '%s - %s' after %d queries", artist, title, song_query_count)

    if not best_vid:
        return None

    threshold = base_threshold + (video_extra if best_rt == "video" else 0.0)
    if best_score >= threshold:
        return (best_vid, yt_title)
    if best_score >= (threshold - BELOW_THRESHOLD_MARGIN):
        log.debug("Accepting below threshold: score %.3f", best_score)
        return (best_vid, yt_title)

    log.debug("Rejecting: score %.3f < threshold %.3f", best_score, threshold)
    return None
