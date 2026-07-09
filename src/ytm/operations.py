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
                    cached_template = cache.get_template(name)
                    if cached_template:
                        cache.set_template(name, found_id, cached_template)
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


def create_playlist_with_items(
    ytm: YTMusic,
    name: str,
    desc: str,
    privacy: str,
    video_ids: list[str],
    cache: PlaylistCache | None = None,
    *,
    role: str | None = None,
) -> str:
    """Create a playlist and cache its template (ID + video IDs)."""
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

    if cache:
        cache.set_template(name, pl_id, video_ids, role=role)

    return pl_id
