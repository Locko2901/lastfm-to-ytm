from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ytmusicapi import YTMusic
from ytmusicapi.exceptions import YTMusicServerError

from ..observability.http_status import extract_http_status, is_rate_limited, is_retryable
from ..ytm import create_playlist_with_items, get_existing_playlist_by_name
from .metrics import _query_counter

if TYPE_CHECKING:
    from ..cache.playlist import PlaylistCache
    from ..cache.search import SearchCache

log = logging.getLogger(__name__)


class InvalidVideoIDsError(Exception):
    """Raised when invalid video IDs are detected during sync."""

    def __init__(self, invalid_ids: list[str]):
        self.invalid_ids = invalid_ids
        super().__init__(f"{len(invalid_ids)} invalid video ID(s) detected: {invalid_ids}")


def _retry_with_backoff(
    func: Callable[..., Any], *args: Any, max_retries: int = 3, initial_delay: float = 1.0, operation: str = "operation", **kwargs: Any
) -> Any:
    """Retry with exponential backoff on rate limit errors."""
    delay = initial_delay
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (RuntimeError, ValueError, OSError, YTMusicServerError) as e:
            last_exception = e
            error_msg = str(e)
            status = extract_http_status(error_msg)

            # Terminal client errors (bad request / conflict) will never succeed.
            if status in (400, 409):
                raise

            if is_retryable(error_msg) and attempt < max_retries - 1:
                log.warning(
                    "%s: %s (retry %d/%d in %.1fs)",
                    operation,
                    f"HTTP {status}" if status else "transient error",
                    attempt + 1,
                    max_retries - 1,
                    delay,
                )
                time.sleep(delay)
                delay *= 2
            else:
                raise

    assert last_exception is not None
    raise last_exception


def _get_playlist_video_ids(ytm: YTMusic, playlist_id: str, max_retries: int = 3) -> list[str]:
    _query_counter.increment("get_playlist")
    log.debug("API Query #%d: get_playlist(%s)", _query_counter.get_count(), playlist_id)

    try:
        playlist = _retry_with_backoff(ytm.get_playlist, playlist_id, limit=None, max_retries=max_retries, operation="get_playlist")
    except Exception as e:
        error_msg = str(e)
        if is_rate_limited(error_msg):
            log.error("Failed to get playlist after retries: HTTP %s - likely rate limited", extract_http_status(error_msg) or "403/429")
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

        def normalize_title(title: str, artists: list[str]) -> str:
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


def _evict_from_cache(search_cache: SearchCache | None, skipped_ids: list[str]) -> None:
    """Evict failed video IDs from the search cache so they get re-resolved next run."""
    if not search_cache or not skipped_ids:
        return
    skipped_set = set(skipped_ids)
    to_evict = [
        (entry.get("artist", ""), entry.get("title", ""), entry.get("video_id"))
        for entry in search_cache.values()
        if entry.get("video_id") in skipped_set
    ]
    for artist, title, vid in to_evict:
        if search_cache.delete_by_track(artist, title):
            log.info("Evicted stale cache entry: %s - %s (video_id=%s)", artist, title, vid)
    if to_evict:
        log.info("Evicted %d stale video IDs from search cache", len(to_evict))


def _validate_video_ids(ytm: YTMusic, video_ids: list[str]) -> list[str]:
    """Validate video IDs by checking them individually. Returns list of invalid IDs."""
    invalid = []
    for vid in video_ids:
        try:
            _query_counter.increment("get_song")
            ytm.get_song(vid)
        except Exception:
            invalid.append(vid)
            log.warning("Invalid video ID detected: %s", vid)
    log.info("Validation complete: %d valid, %d invalid out of %d", len(video_ids) - len(invalid), len(invalid), len(video_ids))
    return invalid


def _replace_playlist_content(ytm: YTMusic, playlist_id: str, video_ids: list[str], max_retries: int = 3) -> None:
    """Replace entire playlist content."""
    precondition_retries = 2
    for precondition_attempt in range(precondition_retries + 1):
        try:
            _do_replace_playlist_content(ytm, playlist_id, video_ids, max_retries)
            return
        except YTMusicServerError as e:
            error_msg = str(e)
            is_retriable = ("Precondition" in error_msg or "409" in error_msg) and precondition_attempt < precondition_retries
            if is_retriable:
                delay = 3 * (2**precondition_attempt)
                log.warning(
                    "Precondition check failed (stale playlist state), re-fetching and retrying (%d/%d in %.1fs)",
                    precondition_attempt + 1,
                    precondition_retries,
                    delay,
                )
                time.sleep(delay)
            else:
                raise


def _reorder_playlist(ytm: YTMusic, playlist_id: str, desired_video_ids: list[str], max_retries: int = 3) -> int:
    """Reorder an existing playlist (same content, possibly different order) to match desired_video_ids.

    Returns the number of move operations performed. Uses YTM's moveItem edit operation
    so no tracks are removed/re-added.
    """
    _query_counter.increment("get_playlist")
    log.debug(
        "API Query #%d: get_playlist(%s) for reorder",
        _query_counter.get_count(),
        playlist_id,
    )
    playlist = _retry_with_backoff(ytm.get_playlist, playlist_id, limit=None, max_retries=max_retries, operation="get_playlist")
    tracks = playlist.get("tracks", []) or []

    current: list[tuple[str, str]] = []
    for t in tracks:
        vid = t.get("videoId")
        svid = t.get("setVideoId")
        if vid and svid and len(vid) == 11:
            current.append((vid, svid))

    moves = 0
    for i, desired_vid in enumerate(desired_video_ids):
        if i >= len(current):
            break
        if current[i][0] == desired_vid:
            continue
        j = next((k for k in range(i + 1, len(current)) if current[k][0] == desired_vid), None)
        if j is None:
            continue
        move_setvid = current[j][1]
        succ_setvid = current[i][1]
        try:
            _query_counter.increment("edit_playlist")
            log.debug(
                "API Query #%d: edit_playlist(%s, moveItem) %d->%d",
                _query_counter.get_count(),
                playlist_id,
                j,
                i,
            )
            _retry_with_backoff(
                ytm.edit_playlist,
                playlist_id,
                moveItem=(move_setvid, succ_setvid),
                max_retries=max_retries,
                operation="reorder",
            )
            moves += 1
        except Exception as e:
            log.warning("Failed to reorder item %s: %s", desired_vid, e)
            continue
        item = current.pop(j)
        current.insert(i, item)

    return moves


def _do_replace_playlist_content(ytm: YTMusic, playlist_id: str, video_ids: list[str], max_retries: int = 3) -> None:
    """Fetch current playlist state, remove all tracks, then add desired tracks."""
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
        try:
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
        except YTMusicServerError as e:
            error_msg = str(e)
            if "400" in error_msg or "409" in error_msg:
                log.warning(
                    "Bulk add failed (%s), validating video IDs...",
                    error_msg.partition(".")[0],
                )
                invalid_ids = _validate_video_ids(ytm, video_ids)
                if invalid_ids:
                    raise InvalidVideoIDsError(invalid_ids) from e
                raise


def sync_playlist(
    ytm: YTMusic,
    playlist_id: str,
    desired_video_ids: list[str],
    *,
    verify_attempts: int = 2,
    accept_substitutions: bool = True,
    max_retries: int = 3,
) -> dict[str, str]:
    """Synchronize a playlist with desired video IDs.

    Returns a dict of detected YouTube substitutions {original_vid: replacement_vid}.
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
        return {}

    unique_count = len(set(desired_video_ids))
    if unique_count < len(desired_video_ids):
        dup_count = len(desired_video_ids) - unique_count
        log.warning(
            "Detected %d duplicate video IDs in desired list (deduplicating before sync)",
            dup_count,
        )
        desired_video_ids = list(dict.fromkeys(desired_video_ids))

    log.debug("Syncing playlist with %d desired videos", len(desired_video_ids))

    try:
        existing_video_ids = _get_playlist_video_ids(ytm, playlist_id, max_retries)
    except Exception as e:
        log.debug("Pre-sync state check failed: %s", e)
        existing_video_ids = None

    if existing_video_ids is not None:
        if existing_video_ids == desired_video_ids:
            log.info("✓ Playlist already in sync (no changes needed)")
            final_count = _query_counter.get_count()
            log.info(
                "Completed using %d API queries (total: %d)",
                final_count - initial_count,
                final_count,
            )
            return {}
        if set(existing_video_ids) == set(desired_video_ids):
            log.info("Content matches but order differs - reordering %d tracks", len(desired_video_ids))
            moves = _reorder_playlist(ytm, playlist_id, desired_video_ids, max_retries)
            log.info("✓ Playlist reordered with %d move operations", moves)
            final_count = _query_counter.get_count()
            log.info(
                "Completed using %d API queries (total: %d)",
                final_count - initial_count,
                final_count,
            )
            return {}

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
            return substitutions

        desired_set = set(desired_video_ids)
        current_set = set(current_video_ids)

        if desired_set == current_set:
            log.info("Content matches after replace but order differs - reordering...")
            moves = _reorder_playlist(ytm, playlist_id, desired_video_ids, max_retries)
            log.info("✓ Playlist sync successful (reordered with %d moves)", moves)
            final_count = _query_counter.get_count()
            log.info(
                "Completed using %d API queries (total: %d)",
                final_count - initial_count,
                final_count,
            )
            return substitutions

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
            return substitutions

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
                    return substitutions

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
    return substitutions


def upsert_playlist(
    ytm: YTMusic,
    playlist_cache: PlaylistCache,
    name: str,
    desc: str,
    privacy: str,
    video_ids: list[str],
    max_retries: int = 3,
) -> str | None:
    """Create or sync a playlist, returning the playlist ID.

    Skips sync when the cached template already matches.
    Returns the playlist ID on success, None on failure.
    """
    existing_id = get_existing_playlist_by_name(ytm, name, cache=playlist_cache)
    template_changed = playlist_cache.template_changed(name, video_ids)

    if existing_id:
        if template_changed:
            log.info("Syncing playlist '%s'...", name)
            sync_playlist(ytm, existing_id, video_ids, max_retries=max_retries)
            playlist_cache.set_template(name, existing_id, video_ids)
        else:
            log.info("Playlist '%s' already up to date", name)
            playlist_cache.touch(name)
        return existing_id

    log.info("Creating playlist '%s'...", name)
    pl_id = create_playlist_with_items(ytm, name, desc, privacy, video_ids, cache=playlist_cache)
    log.info(
        "Created playlist '%s' with %d tracks: https://music.youtube.com/playlist?list=%s",
        name,
        len(video_ids),
        pl_id,
    )
    return pl_id
