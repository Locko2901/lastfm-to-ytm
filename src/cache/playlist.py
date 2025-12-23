from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from . import JSONCache

if TYPE_CHECKING:
    from ytmusicapi import YTMusic

log = logging.getLogger(__name__)


class PlaylistCache(JSONCache):
    """Persistent cache for playlist IDs and desired state (template)."""

    def __init__(self, cache_file: str):
        cache_path = Path(cache_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(cache_file)
        self._load()

    def get_id(self, playlist_name: str) -> str | None:
        entry = self._cache.get(playlist_name)
        if entry and isinstance(entry, dict):
            playlist_id = entry.get("id")
            if playlist_id:
                log.debug("Cache hit: '%s' -> %s", playlist_name, playlist_id)
                self._metrics.record_hit()
                return playlist_id

        log.debug("Cache miss: '%s'", playlist_name)
        self._metrics.record_miss()
        return None

    def get_template(self, playlist_name: str) -> list[str] | None:
        entry = self._cache.get(playlist_name)
        if entry and isinstance(entry, dict):
            video_ids = entry.get("video_ids")
            if video_ids:
                log.debug(
                    "Template hit: '%s' with %d video IDs",
                    playlist_name,
                    len(video_ids),
                )
                return video_ids
        return None

    def set_template(self, playlist_name: str, playlist_id: str, video_ids: list[str]) -> None:
        log.info(
            "Caching template: '%s' -> %s (%d videos)",
            playlist_name,
            playlist_id,
            len(video_ids),
        )
        self._cache[playlist_name] = {
            "id": playlist_id,
            "video_ids": video_ids,
            "last_updated": datetime.now(UTC).isoformat(),
        }
        self._save()

    def template_changed(self, playlist_name: str, new_video_ids: list[str]) -> bool:
        cached_ids = self.get_template(playlist_name)
        if not cached_ids:
            return True

        if cached_ids != new_video_ids:
            log.info(
                "Template changed for '%s': %d videos -> %d videos",
                playlist_name,
                len(cached_ids),
                len(new_video_ids),
            )
            return True

        log.debug("Template unchanged for '%s'", playlist_name)
        return False

    def remove(self, playlist_name: str) -> None:
        if playlist_name in self._cache:
            log.info("Removing from cache: '%s'", playlist_name)
            del self._cache[playlist_name]
            self._save()

    def verify_exists(self, ytm: YTMusic, playlist_name: str) -> bool:
        """Verify cached playlist still exists on YouTube Music.

        Args:
            ytm: YTMusic client instance
            playlist_name: Name of the playlist to verify

        Returns:
            True if playlist exists, False if it was removed from cache
        """
        playlist_id = self.get_id(playlist_name)
        if not playlist_id:
            return False

        try:
            playlist = ytm.get_playlist(playlist_id, limit=0)
            if playlist and playlist.get("id") == playlist_id:
                log.debug("Verified playlist '%s' still exists", playlist_name)
                return True
        except Exception as e:
            error_str = str(e)
            if "Unable to find 'contents'" in error_str or "404" in error_str:
                log.info(
                    "Cached playlist '%s' (%s) was deleted, removing from cache",
                    playlist_name,
                    playlist_id,
                )
            else:
                log.warning(
                    "Could not verify playlist '%s' (%s): %s",
                    playlist_name,
                    playlist_id,
                    error_str[:100],
                )

        self.remove(playlist_name)
        return False
