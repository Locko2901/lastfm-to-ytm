from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from ytmusicapi import YTMusic

    from ..cache.playlist import PlaylistCache

log = logging.getLogger(__name__)


def get_existing_playlist_by_name(
    ytm: YTMusic,
    name: str,
    cache: PlaylistCache | None = None,
    verify_cached: bool = True,
) -> str | None:
    """Find playlist by name using cache-first approach."""
    if cache:
        cached_id = cache.get_id(name)
        if cached_id:
            if verify_cached:
                if cache.verify_exists(ytm, name):
                    return cached_id
            else:
                return cached_id

    log.debug("Checking API for playlist '%s'", name)
    try:
        playlists = ytm.get_library_playlists(limit=1000)
        if playlists:
            matches = []
            for p in playlists:
                if p.get("title") == name:
                    playlist_id = p.get("playlistId")
                    matches.append(playlist_id)

            if len(matches) > 1:
                log.warning(
                    "Found %d playlists with name '%s': %s. Using first match.",
                    len(matches),
                    name,
                    matches,
                )

            if matches:
                found_id = matches[0]
                if found_id and cache:
                    cache.track_id(name, found_id)
                return found_id
    except Exception as e:
        log.warning("Failed to get library playlists: %s", e)

    return None


def get_or_rename_playlist(
    ytm: YTMusic,
    name: str,
    cache: PlaylistCache | None = None,
    *,
    role: str | None = None,
) -> str | None:
    """Resolve a managed playlist's ID, renaming it in place if it was renamed.

    First tries the normal name-based lookup. If that misses but the cache holds
    an entry with the same ``role`` under a different name, the playlist was
    renamed (e.g. the user changed ``PLAYLIST_NAME``): the existing YTM playlist
    is retitled via ``edit_playlist`` and the cache key migrated, avoiding a
    duplicate playlist. Returns the playlist ID, or ``None`` when it must be
    created fresh.
    """
    existing_id = get_existing_playlist_by_name(ytm, name, cache=cache)
    if existing_id:
        return existing_id

    if cache is None or not role:
        return None

    prev = cache.find_by_role(role)
    if not prev:
        return None
    prev_name, prev_id = prev
    if prev_name == name or not prev_id:
        return None

    try:
        playlist = ytm.get_playlist(prev_id, limit=0)
        if not playlist or playlist.get("id") != prev_id:
            cache.remove(prev_name)
            return None
    except Exception as e:
        error_str = str(e)
        if "Unable to find 'contents'" in error_str or "404" in error_str:
            log.info("Previously-tracked playlist '%s' (%s) is gone, dropping from cache", prev_name, prev_id)
            cache.remove(prev_name)
        else:
            log.warning("Could not verify playlist '%s' for rename: %s", prev_name, e)
        return None

    log.info("Detected playlist rename '%s' -> '%s' (%s); renaming in place", prev_name, name, prev_id)
    try:
        ytm.edit_playlist(prev_id, title=name)
    except Exception as e:
        log.warning("Failed to rename playlist '%s' -> '%s' on YouTube Music: %s", prev_name, name, e)
        return None
    cache.rename(prev_name, name)
    return prev_id


def add_items_fallback(ytm: YTMusic, pl_id: str, video_ids: list[str], chunk_size: int = 75) -> None:
    """Add items to playlist in chunks with single-item fallback on error."""
    for start in range(0, len(video_ids), chunk_size):
        chunk = video_ids[start : start + chunk_size]
        try:
            ytm.add_playlist_items(pl_id, chunk, duplicates=False)
        except Exception as e:
            log.debug("Chunk add failed, trying one-by-one: %s", e)
            for vid in chunk:
                try:
                    ytm.add_playlist_items(pl_id, [vid], duplicates=False)
                except Exception as e2:
                    log.debug("Failed to add video %s: %s", vid, e2)


def _resolve_canonical_playlist_id(ytm: YTMusic, playlist_id: str, max_retries: int = 3) -> str:
    """Resolve the canonical library playlist ID for a freshly-created playlist.

    ``create_playlist`` returns YTM's compact playlist ID form; ``get_playlist``
    (like ``get_library_playlists``) exposes the canonical ID. Fetch the playlist
    once - with the project's standard exponential backoff, since the API is
    flaky - and read back its canonical ``id``. Falls back to the create-time ID
    on any failure so a transient hiccup never blocks the sync.
    """
    from ..playlist.sync import _retry_with_backoff

    try:
        playlist = _retry_with_backoff(
            ytm.get_playlist,
            playlist_id,
            limit=0,
            max_retries=max_retries,
            operation="get_playlist",
        )
    except Exception as e:
        log.warning("Could not resolve canonical ID for playlist %s: %s", playlist_id, e)
        return playlist_id

    canonical = playlist.get("id") if isinstance(playlist, dict) else None
    if isinstance(canonical, str) and canonical:
        if canonical != playlist_id:
            log.info("Resolved canonical playlist ID: %s -> %s", playlist_id, canonical)
        return canonical
    return playlist_id


def create_playlist_with_items(
    ytm: YTMusic,
    name: str,
    desc: str,
    privacy: str,
    video_ids: list[str],
    cache: PlaylistCache | None = None,
    *,
    role: str | None = None,
    max_retries: int = 3,
) -> str:
    """Create a playlist and cache its template (ID + video IDs).

    ``create_playlist`` returns YouTube Music's compact playlist ID form, which
    differs from the canonical ID exposed by ``get_library_playlists`` (there is
    no offline conversion between the two). Immediately after creating, the
    canonical ID is resolved via ``get_playlist`` so the cache stores the
    authoritative ID and every later operation references the playlist by it.
    """
    try:
        pl_id = cast("str", ytm.create_playlist(name, desc, privacy_status=privacy, video_ids=video_ids))
    except TypeError:
        log.warning("create_playlist with video_ids not supported, using fallback")
        pl_id = cast("str", ytm.create_playlist(name, desc, privacy_status=privacy))
        add_items_fallback(ytm, pl_id, video_ids)
    except Exception as e:
        log.warning("create_playlist with video_ids failed: %s, using fallback", e)
        pl_id = cast("str", ytm.create_playlist(name, desc, privacy_status=privacy))
        add_items_fallback(ytm, pl_id, video_ids)

    log.info("Created playlist '%s' with ID: %s", name, pl_id)

    pl_id = _resolve_canonical_playlist_id(ytm, pl_id, max_retries=max_retries)

    if cache:
        cache.set_template(name, pl_id, video_ids, role=role)

    return pl_id
