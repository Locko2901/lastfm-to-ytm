from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import JSONCache

if TYPE_CHECKING:
    from ytmusicapi import YTMusic

log = logging.getLogger(__name__)


class PlaylistCache(JSONCache[Any]):
    """Persistent cache for playlist IDs and desired state (template)."""

    def __init__(self, cache_file: str):
        cache_path = Path(cache_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(cache_file)
        self._load()

    def get_id(self, playlist_name: str) -> str | None:
        """Get cached playlist ID."""
        entry = self._cache.get(playlist_name)
        if entry and isinstance(entry, dict):
            playlist_id = entry.get("id")
            if playlist_id:
                log.debug("Cache hit: '%s' -> %s", playlist_name, playlist_id)
                self._metrics.record_hit()
                return str(playlist_id)

        log.debug("Cache miss: '%s'", playlist_name)
        self._metrics.record_miss()
        return None

    def get_template(self, playlist_name: str) -> list[str] | None:
        """Get cached video IDs template."""
        entry = self._cache.get(playlist_name)
        if entry and isinstance(entry, dict):
            video_ids = entry.get("video_ids")
            if video_ids:
                log.debug(
                    "Template hit: '%s' with %d video IDs",
                    playlist_name,
                    len(video_ids),
                )
                return list(video_ids)
        return None

    def set_template(self, playlist_name: str, playlist_id: str, video_ids: list[str]) -> None:
        """Cache playlist ID and template."""
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
        """Check if template changed."""
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

    def touch(self, playlist_name: str) -> None:
        """Update the ``last_updated`` timestamp without modifying the template.

        Used after a sync run that produced no changes, so the dashboard's
        "last sync" stat reflects the most recent sync attempt rather than the
        last time the playlist's contents actually changed.
        """
        entry = self._cache.get(playlist_name)
        if not entry or not isinstance(entry, dict):
            return
        entry["last_updated"] = datetime.now(UTC).isoformat()
        self._save()

    def remove(self, playlist_name: str) -> None:
        """Remove playlist from cache."""
        if playlist_name in self._cache:
            log.info("Removing from cache: '%s'", playlist_name)
            del self._cache[playlist_name]
            self._save()

    def remove_video_id(self, playlist_name: str, video_id: str) -> bool:
        """Remove a single video ID from a playlist's cached template.

        Returns True if removed, False if playlist or video_id not found.
        """
        entry = self._cache.get(playlist_name)
        if not entry or not isinstance(entry, dict):
            return False
        video_ids = entry.get("video_ids") or []
        if video_id not in video_ids:
            return False
        entry["video_ids"] = [v for v in video_ids if v != video_id]
        entry["last_updated"] = datetime.now(UTC).isoformat()
        self._save()
        log.info("Removed video %s from cached template '%s'", video_id, playlist_name)
        return True

    def summary(self) -> list[dict[str, Any]]:
        """List cached playlists with id, video_count, last_updated."""
        out: list[dict[str, Any]] = []
        for name, entry in self._cache.items():
            if not isinstance(entry, dict):
                continue
            out.append(
                {
                    "name": name,
                    "id": entry.get("id"),
                    "video_count": len(entry.get("video_ids") or []),
                    "last_updated": entry.get("last_updated"),
                }
            )
        out.sort(key=lambda x: x["name"].lower())
        return out

    def get_video_ids(self, playlist_name: str) -> list[str]:
        """Get cached video IDs for a playlist (or empty list)."""
        entry = self._cache.get(playlist_name)
        if entry and isinstance(entry, dict):
            return list(entry.get("video_ids") or [])
        return []

    def prune_old_weeklies(self, base_prefix: str, keep_count: int = 1) -> list[str]:
        """Remove old weekly playlists."""
        import re
        from datetime import date

        if keep_count <= 0:
            keep_count = 1

        marker = f"{base_prefix} week of "
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

        weekly_entries: list[tuple[date, str]] = []
        for name in list(self._cache.keys()):
            if not name.startswith(marker):
                continue
            tail = name[len(marker) :].strip()
            if date_pattern.match(tail):
                try:
                    d = date.fromisoformat(tail)
                    weekly_entries.append((d, name))
                except Exception:
                    continue

        if len(weekly_entries) <= keep_count:
            return []

        weekly_entries.sort(key=lambda x: x[0], reverse=True)
        to_remove = weekly_entries[keep_count:]

        removed = []
        for _, name in to_remove:
            log.info("Pruning old weekly from cache: '%s'", name)
            del self._cache[name]
            removed.append(name)

        if removed:
            self._save()

        return removed

    def verify_exists(self, ytm: YTMusic, playlist_name: str) -> bool:
        """Verify playlist still exists on YTM."""
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
