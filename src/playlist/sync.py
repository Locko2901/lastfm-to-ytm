from __future__ import annotations

import logging
import time
from typing import Any

from ytmusicapi import YTMusic

from .metrics import _query_counter

log = logging.getLogger(__name__)


def _retry_with_backoff(func, *args, max_retries: int = 3, initial_delay: float = 1.0, operation: str = "operation", **kwargs) -> Any:
    """Retry with exponential backoff on rate limit errors."""
    delay = initial_delay
    last_exception = None

    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (RuntimeError, ValueError, OSError) as e:
            last_exception = e
            error_msg = str(e)

            is_rate_limit = "403" in error_msg or "Forbidden" in error_msg or ("Expecting value" in error_msg and attempt < max_retries - 1)

            if is_rate_limit and attempt < max_retries - 1:
                log.warning(
                    "%s: rate limit (retry %d/%d in %.1fs)",
                    operation,
                    attempt + 1,
                    max_retries - 1,
                    delay,
                )
                time.sleep(delay)
                delay *= 2
            else:
                raise

    raise last_exception


def _get_playlist_video_ids(ytm: YTMusic, playlist_id: str, max_retries: int = 3) -> list[str]:
    _query_counter.increment("get_playlist")
    log.debug("API Query #%d: get_playlist(%s)", _query_counter.get_count(), playlist_id)

    try:
        playlist = _retry_with_backoff(ytm.get_playlist, playlist_id, limit=None, max_retries=max_retries, operation="get_playlist")
    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg or "Forbidden" in error_msg:
            log.error("Failed to get playlist after retries: HTTP 403 - Likely rate limited")
        elif "Expecting value" in error_msg:
            log.error("Failed to get playlist after retries: Invalid JSON response from API")
        else:
            log.error("Failed to get playlist: %s", error_msg)
        raise

    tracks = playlist.get("tracks", [])

    video_ids = []
    for track in tracks:
        video_id = track.get("videoId")
        if video_id and len(video_id) == 11:
            video_ids.append(video_id)

    log.debug("Retrieved %d video IDs from playlist", len(video_ids))
    return video_ids


def _are_same_song(ytm: YTMusic, vid1: str, vid2: str) -> bool:
    if vid1 == vid2:
        return True

    try:
        _query_counter.increment("get_song")
        log.debug("API Query #%d: get_song(%s)", _query_counter.get_count(), vid1)
        info1 = ytm.get_song(vid1)

        _query_counter.increment("get_song")
        log.debug("API Query #%d: get_song(%s)", _query_counter.get_count(), vid2)
        info2 = ytm.get_song(vid2)

        if not info1 or not info2:
            return False

        title1 = info1.get("videoDetails", {}).get("title", info1.get("title", "")).strip().lower()
        title2 = info2.get("videoDetails", {}).get("title", info2.get("title", "")).strip().lower()

        artists1 = []
        artists2 = []
        if "artists" in info1:
            artists1 = [a.get("name", "").lower() for a in info1["artists"] if a.get("name")]
        elif "videoDetails" in info1:
            author = info1["videoDetails"].get("author", "").strip().lower()
            if author:
                artists1 = [author]

        if "artists" in info2:
            artists2 = [a.get("name", "").lower() for a in info2["artists"] if a.get("name")]
        elif "videoDetails" in info2:
            author = info2["videoDetails"].get("author", "").strip().lower()
            if author:
                artists2 = [author]

        def normalize_title(title, artists):
            """Remove artist names, common suffixes, and extra formatting from title."""
            normalized = title
            for artist in artists:
                if normalized.startswith(artist + " - "):
                    normalized = normalized[len(artist) + 3 :]
                if normalized.startswith(artist + " – "):
                    normalized = normalized[len(artist) + 3 :]
            for suffix in [
                " (audio)",
                " (official audio)",
                " (official video)",
                " (lyric video)",
                " (lyrics)",
                " [official audio]",
                " [audio]",
                " - audio",
                " - official audio",
            ]:
                if normalized.endswith(suffix):
                    normalized = normalized[: -len(suffix)]
            return normalized.strip()

        norm_title1 = normalize_title(title1, artists1)
        norm_title2 = normalize_title(title2, artists2)

        artist_match = artists1 and artists2 and any(a in artists2 for a in artists1)

        if norm_title1 and norm_title2 and norm_title1 == norm_title2 and artist_match:
            log.info("Detected YouTube substitution: %s -> %s (same song)", vid1, vid2)
            log.debug(
                "  Title match: '%s' = '%s', Artists: %s",
                norm_title1,
                norm_title2,
                artists1,
            )
            return True

        if artist_match and norm_title1 and norm_title2 and (norm_title1 in norm_title2 or norm_title2 in norm_title1):
            min_len = min(len(norm_title1), len(norm_title2))
            if min_len >= 3:
                log.info(
                    "Detected YouTube substitution: %s -> %s (same song)",
                    vid1,
                    vid2,
                )
                log.debug(
                    "  Title contains match: '%s' ~ '%s', Artists: %s",
                    norm_title1,
                    norm_title2,
                    artists1,
                )
                return True

        log.debug(
            "Videos are different songs: '%s' by %s vs '%s' by %s",
            title1[:40],
            artists1,
            title2[:40],
            artists2,
        )
        return False

    except Exception as e:
        log.debug("Error checking if videos are same song: %s", e)
        return False


def _replace_playlist_content(ytm: YTMusic, playlist_id: str, video_ids: list[str], max_retries: int = 3) -> None:
    """Replace entire playlist content with new video IDs."""
    _query_counter.increment("get_playlist")
    log.debug(
        "API Query #%d: get_playlist(%s) for replacement",
        _query_counter.get_count(),
        playlist_id,
    )
    playlist = _retry_with_backoff(ytm.get_playlist, playlist_id, limit=None, max_retries=max_retries, operation="get_playlist")
    tracks = playlist.get("tracks", [])

    if tracks:
        videos_to_remove = []
        for track in tracks:
            set_video_id = track.get("setVideoId")
            video_id = track.get("videoId")
            if set_video_id:
                videos_to_remove.append({"setVideoId": set_video_id, "videoId": video_id})

        if videos_to_remove:
            _query_counter.increment("remove_playlist_items")
            log.debug(
                "API Query #%d: remove_playlist_items(%s, %d items)",
                _query_counter.get_count(),
                playlist_id,
                len(videos_to_remove),
            )
            _retry_with_backoff(
                ytm.remove_playlist_items,
                playlist_id,
                videos_to_remove,
                max_retries=max_retries,
                operation="remove_items",
            )
            log.debug("Removed %d tracks from playlist", len(videos_to_remove))

    if video_ids:
        _query_counter.increment("add_playlist_items")
        log.debug(
            "API Query #%d: add_playlist_items(%s, %d items)",
            _query_counter.get_count(),
            playlist_id,
            len(video_ids),
        )
        _retry_with_backoff(
            ytm.add_playlist_items,
            playlist_id,
            video_ids,
            duplicates=False,
            max_retries=max_retries,
            operation="add_items",
        )
        log.debug("Added %d tracks to playlist", len(video_ids))


def sync_playlist(
    ytm: YTMusic,
    playlist_id: str,
    desired_video_ids: list[str],
    *,
    verify_attempts: int = 2,
    accept_substitutions: bool = True,
    max_retries: int = 3,
) -> None:
    """Synchronize a playlist with desired video IDs.

    Simple flow:
    1. Replace playlist content
    2. Verify it matches
    3. If not, check for YouTube substitutions
    4. Retry or accept substitutions
    """
    initial_count = _query_counter.get_count()
    log.info(
        "Starting playlist sync for %s (current query count: %d)",
        playlist_id,
        initial_count,
    )

    desired_video_ids = [vid for vid in desired_video_ids if isinstance(vid, str) and len(vid) == 11]
    if not desired_video_ids:
        log.warning("No valid video IDs provided")
        return

    # Check for duplicates and warn (should not happen, but defensive check)
    unique_count = len(set(desired_video_ids))
    if unique_count < len(desired_video_ids):
        dup_count = len(desired_video_ids) - unique_count
        log.warning(
            "Detected %d duplicate video IDs in desired list (deduplicating before sync)",
            dup_count,
        )
        # Deduplicate while preserving order
        desired_video_ids = list(dict.fromkeys(desired_video_ids))

    log.debug("Syncing playlist with %d desired videos", len(desired_video_ids))

    _replace_playlist_content(ytm, playlist_id, desired_video_ids, max_retries)

    substitutions: dict[str, str] = {}

    for attempt in range(verify_attempts + 1):
        current_video_ids = _get_playlist_video_ids(ytm, playlist_id, max_retries)

        if current_video_ids == desired_video_ids:
            log.info("✓ Playlist sync successful (exact match)")
            final_count = _query_counter.get_count()
            log.info(
                "Completed using %d API queries (total: %d)",
                final_count - initial_count,
                final_count,
            )
            return

        desired_set = set(desired_video_ids)
        current_set = set(current_video_ids)

        if desired_set == current_set:
            log.info("✓ Playlist sync successful (same content, different order)")
            log.debug("Order mismatch is acceptable for this use case")
            final_count = _query_counter.get_count()
            log.info(
                "Completed using %d API queries (total: %d)",
                final_count - initial_count,
                final_count,
            )
            return

        missing = desired_set - current_set
        extra = current_set - desired_set

        if not missing and not extra:
            log.info("✓ Playlist sync successful")
            final_count = _query_counter.get_count()
            log.info(
                "Completed using %d API queries (total: %d)",
                final_count - initial_count,
                final_count,
            )
            return

        log.debug(
            "Playlist mismatch - missing: %d, extra: %d (attempt %d/%d)",
            len(missing),
            len(extra),
            attempt + 1,
            verify_attempts + 1,
        )

        if accept_substitutions:
            new_substitutions = {}
            for missing_vid in missing:
                for extra_vid in extra:
                    if _are_same_song(ytm, missing_vid, extra_vid):
                        new_substitutions[missing_vid] = extra_vid
                        break

            if new_substitutions:
                substitutions.update(new_substitutions)
                log.info("Found %d YouTube substitutions", len(new_substitutions))

                adjusted_desired = [substitutions.get(vid, vid) for vid in desired_video_ids]

                if set(adjusted_desired) == current_set:
                    log.info(
                        "✓ Playlist sync successful (with %d substitutions)",
                        len(substitutions),
                    )
                    for orig, sub in substitutions.items():
                        log.info("  Substitution: %s -> %s", orig, sub)
                    final_count = _query_counter.get_count()
                    log.info(
                        "Completed using %d API queries (total: %d)",
                        final_count - initial_count,
                        final_count,
                    )
                    return

                desired_video_ids = adjusted_desired
                desired_set = set(desired_video_ids)

        if attempt < verify_attempts:
            log.debug("Retrying playlist sync...")
            _replace_playlist_content(ytm, playlist_id, desired_video_ids, max_retries)
        else:
            similarity = len(desired_set & current_set) / len(desired_set) if desired_set else 0.0

            if similarity >= 0.9:
                log.info(
                    "✓ Playlist sync acceptable (%.1f%% match with %d substitutions)",
                    similarity * 100,
                    len(substitutions),
                )
            else:
                log.warning("⚠ Playlist sync incomplete (%.1f%% match)", similarity * 100)
                log.warning("Missing videos: %s", list(missing)[:5])
                log.warning("Extra videos: %s", list(extra)[:5])

    final_count = _query_counter.get_count()
    log.info(
        "Completed using %d API queries (total: %d)",
        final_count - initial_count,
        final_count,
    )
