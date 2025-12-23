from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import JSONCache

log = logging.getLogger(__name__)

# Sentinel value to distinguish "not found" from "not in cache"
NOT_FOUND = "__NOT_FOUND__"


class SearchCache(JSONCache):
    """Persistent cache for artist/title -> video ID mappings."""

    def __init__(self, cache_file: str, ttl_days: int = 30, notfound_ttl_days: int = 7):
        """Initialize search cache.

        Args:
            cache_file: Path to cache file
            ttl_days: TTL for successful lookups (0 = no expiry)
            notfound_ttl_days: TTL for not-found entries (0 = don't cache not-found)
        """
        cache_path = Path(cache_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(cache_file)
        self.ttl_days = ttl_days
        self.notfound_ttl_days = notfound_ttl_days
        self._load()
        self._clean_expired()

    def _clean_expired(self) -> None:
        now = datetime.now(UTC)
        expired_keys = []

        for key, entry in self._cache.items():
            timestamp_str = entry.get("timestamp")
            if not timestamp_str:
                expired_keys.append(key)
                continue

            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except Exception:
                expired_keys.append(key)
                continue

            video_id = entry.get("video_id")
            if video_id:
                # Successful lookup - use main TTL
                if self.ttl_days > 0:
                    cutoff = now - timedelta(days=self.ttl_days)
                    if timestamp < cutoff:
                        expired_keys.append(key)
            # Not-found entry - use shorter TTL
            elif self.notfound_ttl_days > 0:
                cutoff = now - timedelta(days=self.notfound_ttl_days)
                if timestamp < cutoff:
                    expired_keys.append(key)
            elif self.notfound_ttl_days == 0:
                # Don't cache not-found at all
                expired_keys.append(key)

        if expired_keys:
            for key in expired_keys:
                del self._cache[key]
            log.info("Cleaned %d expired/invalid cache entries", len(expired_keys))
            self._save()

    def _make_key(self, artist: str, title: str) -> str:
        return f"{artist.lower()}|{title.lower()}"

    def get(self, artist: str, title: str) -> str | None:
        """Get cached video ID for artist/title.

        Returns:
            - Video ID string if found
            - NOT_FOUND sentinel if previously searched and not found
            - None if not in cache (needs search)
        """
        key = self._make_key(artist, title)
        entry = self._cache.get(key)

        if not entry:
            self._metrics.record_miss()
            return None

        now = datetime.now(UTC)
        timestamp_str = entry.get("timestamp")
        if timestamp_str:
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except Exception:
                self._metrics.record_miss()
                return None

            video_id = entry.get("video_id")
            if video_id:
                # Check main TTL for successful lookups
                if self.ttl_days > 0:
                    cutoff = now - timedelta(days=self.ttl_days)
                    if timestamp < cutoff:
                        self._metrics.record_miss()
                        return None
                self._metrics.record_hit()
                return video_id
            # Check not-found TTL
            if self.notfound_ttl_days > 0:
                cutoff = now - timedelta(days=self.notfound_ttl_days)
                if timestamp < cutoff:
                    self._metrics.record_miss()
                    return None
                self._metrics.record_hit()
                return NOT_FOUND
            # Not caching not-found
            self._metrics.record_miss()
            return None

        self._metrics.record_miss()
        return None

    def set(self, artist: str, title: str, video_id: str | None) -> None:
        """Cache a video ID for artist/title."""
        # Don't cache not-found if notfound_ttl is 0
        if video_id is None and self.notfound_ttl_days == 0:
            return

        key = self._make_key(artist, title)
        self._cache[key] = {
            "artist": artist,
            "title": title,
            "video_id": video_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._save()

    def stats(self) -> dict[str, int]:
        """Get cache statistics."""
        total = len(self._cache)
        found = sum(1 for entry in self._cache.values() if entry.get("video_id"))
        notfound = total - found
        return {"total": total, "found": found, "notfound": notfound}


class SearchOverrides(JSONCache):
    """Manual overrides and blacklist for search results."""

    def __init__(self, overrides_file: str):
        cache_path = Path(overrides_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(overrides_file)
        self._load()
        self._ensure_sections()

    def _ensure_sections(self) -> None:
        """Ensure _overrides and _blacklist sections exist."""
        if not isinstance(self._cache, dict):
            self._cache = {}

        if "_overrides" not in self._cache:
            self._cache["_overrides"] = {}
        if "_blacklist" not in self._cache:
            self._cache["_blacklist"] = {}

    def _make_key(self, artist: str, title: str) -> str:
        return f"{artist.lower()}|{title.lower()}"

    def get(self, artist: str, title: str) -> str | None:
        """Get manual override video ID for artist/title.

        Args:
            artist: Artist name
            title: Track title

        Returns:
            Video ID if override exists, None otherwise
        """
        key = self._make_key(artist, title)
        overrides = self._cache.get("_overrides", {})
        entry = overrides.get(key)

        if not entry:
            return None

        video_id = entry.get("video_id")
        if video_id:
            log.debug("Search override hit: %s - %s -> %s", artist, title, video_id)
            self._metrics.record_hit()
            return video_id

        return None

    def is_blacklisted(self, artist: str, title: str) -> bool:
        """Check if artist/title is blacklisted.

        Args:
            artist: Artist name
            title: Track title

        Returns:
            True if track is blacklisted, False otherwise
        """
        key = self._make_key(artist, title)
        blacklist = self._cache.get("_blacklist", {})

        if key in blacklist:
            entry = blacklist[key]
            reason = entry.get("reason", "no reason given")
            log.info("Blacklisted track skipped: %s - %s (reason: %s)", artist, title, reason)
            return True

        return False

    def set(self, artist: str, title: str, video_id: str, reason: str = "") -> None:
        """Add a manual override for artist/title.

        Args:
            artist: Artist name
            title: Track title
            video_id: YouTube video ID
            reason: Optional reason for the override (e.g., "search found wrong song")
        """
        key = self._make_key(artist, title)
        overrides = self._cache.get("_overrides", {})
        overrides[key] = {
            "artist": artist,
            "title": title,
            "video_id": video_id,
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._cache["_overrides"] = overrides
        log.info("Added search override: %s - %s -> %s", artist, title, video_id)
        self._save()

    def blacklist(self, artist: str, title: str, reason: str = "") -> None:
        """Add a track to the blacklist.

        Args:
            artist: Artist name
            title: Track title
            reason: Optional reason for blacklisting (e.g., "inappropriate", "duplicate")
        """
        key = self._make_key(artist, title)
        blacklist = self._cache.get("_blacklist", {})
        blacklist[key] = {
            "artist": artist,
            "title": title,
            "reason": reason,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._cache["_blacklist"] = blacklist
        log.info("Added to blacklist: %s - %s (reason: %s)", artist, title, reason or "none")
        self._save()

    def remove_blacklist(self, artist: str, title: str) -> bool:
        """Remove a track from the blacklist.

        Args:
            artist: Artist name
            title: Track title

        Returns:
            True if track was removed, False if it wasn't blacklisted
        """
        key = self._make_key(artist, title)
        blacklist = self._cache.get("_blacklist", {})

        if key in blacklist:
            del blacklist[key]
            self._cache["_blacklist"] = blacklist
            log.info("Removed from blacklist: %s - %s", artist, title)
            self._save()
            return True
        return False

    def remove(self, artist: str, title: str) -> bool:
        """Remove a manual override.

        Args:
            artist: Artist name
            title: Track title

        Returns:
            True if override was removed, False if it didn't exist
        """
        key = self._make_key(artist, title)
        overrides = self._cache.get("_overrides", {})

        if key in overrides:
            del overrides[key]
            self._cache["_overrides"] = overrides
            log.info("Removed search override: %s - %s", artist, title)
            self._save()
            return True
        return False

    def stats(self) -> dict[str, int]:
        """Get override statistics.

        Returns:
            Dictionary with override and blacklist statistics
        """
        overrides = self._cache.get("_overrides", {})
        blacklist = self._cache.get("_blacklist", {})

        return {"total_overrides": len(overrides), "total_blacklisted": len(blacklist)}
