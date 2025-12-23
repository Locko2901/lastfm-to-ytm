from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
    """Find playlist by name using cache-first approach.

    Args:
        ytm: YTMusic client
        name: Playlist name
        cache: PlaylistCache instance (optional)
        verify_cached: Verify cached playlist still exists

    Returns:
        Playlist ID if found, None otherwise
    """
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
                if cache:
                    cached_template = cache.get_template(name)
                    if cached_template:
                        cache.set_template(name, found_id, cached_template)
                return found_id
    except Exception as e:
        log.warning("Failed to get library playlists: %s", e)

    return None


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
) -> str:
    """Create a playlist and cache its template (ID + video IDs).

    Args:
        ytm: YTMusic client
        name: Playlist name
        desc: Playlist description
        privacy: Privacy status (PUBLIC/PRIVATE)
        video_ids: List of video IDs to add
        cache: PlaylistCache instance (optional)

    Returns:
        Created playlist ID
    """
    try:
        pl_id = ytm.create_playlist(name, desc, privacy_status=privacy, video_ids=video_ids)
    except TypeError:
        log.warning("create_playlist with video_ids not supported, using fallback")
        pl_id = ytm.create_playlist(name, desc, privacy_status=privacy)
        add_items_fallback(ytm, pl_id, video_ids)
    except Exception as e:
        log.warning("create_playlist with video_ids failed: %s, using fallback", e)
        pl_id = ytm.create_playlist(name, desc, privacy_status=privacy)
        add_items_fallback(ytm, pl_id, video_ids)

    log.info("Created playlist '%s' with ID: %s", name, pl_id)

    if cache:
        cache.set_template(name, pl_id, video_ids)

    return pl_id
