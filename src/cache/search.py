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
                if self.ttl_days > 0:
                    cutoff = now - timedelta(days=self.ttl_days)
                    if timestamp < cutoff:
                        expired_keys.append(key)
            elif self.notfound_ttl_days > 0:
                cutoff = now - timedelta(days=self.notfound_ttl_days)
                if timestamp < cutoff:
                    expired_keys.append(key)
            elif self.notfound_ttl_days == 0:
                expired_keys.append(key)

        if expired_keys:
            for key in expired_keys:
                del self._cache[key]
            log.info("Cleaned %d expired/invalid cache entries", len(expired_keys))
            self._save()

    def _make_key(self, artist: str, title: str) -> str:
        return f"{artist.lower()}|{title.lower()}"

    def get(self, artist: str, title: str) -> str | None:
        """Get cached video ID, or NOT_FOUND sentinel if previously not found."""
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
                if self.ttl_days > 0:
                    cutoff = now - timedelta(days=self.ttl_days)
                    if timestamp < cutoff:
                        self._metrics.record_miss()
                        return None
                self._metrics.record_hit()
                return video_id
            if self.notfound_ttl_days > 0:
                cutoff = now - timedelta(days=self.notfound_ttl_days)
                if timestamp < cutoff:
                    self._metrics.record_miss()
                    return None
                self._metrics.record_hit()
                return NOT_FOUND
            self._metrics.record_miss()
            return None

        self._metrics.record_miss()
        return None

    def get_entry(self, artist: str, title: str) -> dict | None:
        """Get full cache entry including yt_title."""
        key = self._make_key(artist, title)
        entry = self._cache.get(key)
        if not entry:
            return None
        return entry

    def set(self, artist: str, title: str, video_id: str | None, yt_title: str | None = None) -> None:
        """Cache video ID and optional YouTube title."""
        if video_id is None and self.notfound_ttl_days == 0:
            return

        key = self._make_key(artist, title)
        entry = {
            "artist": artist,
            "title": title,
            "video_id": video_id,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if yt_title:
            entry["yt_title"] = yt_title
        self._cache[key] = entry
        self._save()

    def items(self) -> list[tuple[str, dict]]:
        """Return all cache entries."""
        return list(self._cache.items())

    def values(self) -> list[dict]:
        """Return all cache entry values."""
        return list(self._cache.values())

    def delete_by_track(self, artist: str, title: str) -> bool:
        """Delete cache entry by artist/title."""
        key = self._make_key(artist, title)
        if key in self._cache:
            del self._cache[key]
            self._save()
            return True
        return False

    def delete_keys(self, keys: list[str]) -> int:
        """Delete multiple entries by raw cache key. Returns count deleted."""
        deleted = 0
        for key in keys:
            if key in self._cache:
                del self._cache[key]
                deleted += 1
        if deleted:
            self._save()
        return deleted

    def clear_notfound(self) -> int:
        """Delete all entries with no video_id. Returns count deleted."""
        keys = [k for k, e in self._cache.items() if not e.get("video_id")]
        return self.delete_keys(keys)

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
        if not isinstance(self._cache, dict):
            self._cache = {}

        if "_overrides" not in self._cache:
            self._cache["_overrides"] = {}
        if "_blacklist" not in self._cache:
            self._cache["_blacklist"] = {}

    def _make_key(self, artist: str, title: str) -> str:
        return f"{artist.lower()}|{title.lower()}"

    def get(self, artist: str, title: str) -> str | None:
        """Get override video ID."""
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
        """Check if track is blacklisted."""
        key = self._make_key(artist, title)
        blacklist = self._cache.get("_blacklist", {})

        return key in blacklist

    def get_blacklist_reason(self, artist: str, title: str) -> str | None:
        """Get blacklist reason, or None if not blacklisted."""
        key = self._make_key(artist, title)
        blacklist = self._cache.get("_blacklist", {})
        entry = blacklist.get(key)
        if entry:
            return entry.get("reason", "no reason given")
        return None

    def set(self, artist: str, title: str, video_id: str, reason: str = "") -> None:
        """Add a manual override for artist/title."""
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
        """Add a track to the blacklist."""
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
        """Remove a track from the blacklist. Returns True if removed."""
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
        """Remove a manual override. Returns True if removed."""
        key = self._make_key(artist, title)
        overrides = self._cache.get("_overrides", {})

        if key in overrides:
            del overrides[key]
            self._cache["_overrides"] = overrides
            log.info("Removed search override: %s - %s", artist, title)
            self._save()
            return True
        return False

    def override_keys(self) -> set[str]:
        """Return the set of override keys (lowercase 'artist|title')."""
        return set(self._cache.get("_overrides", {}).keys())

    def blacklist_keys(self) -> set[str]:
        """Return the set of blacklist keys (lowercase 'artist|title')."""
        return set(self._cache.get("_blacklist", {}).keys())

    def override_items(self) -> list[tuple[str, dict]]:
        """Return all override entries as (key, data) pairs."""
        return list(self._cache.get("_overrides", {}).items())

    def blacklist_items(self) -> list[tuple[str, dict]]:
        """Return all blacklist entries as (key, data) pairs."""
        return list(self._cache.get("_blacklist", {}).items())

    def stats(self) -> dict[str, int]:
        """Get override statistics."""
        overrides = self._cache.get("_overrides", {})
        blacklist = self._cache.get("_blacklist", {})

        return {"total_overrides": len(overrides), "total_blacklisted": len(blacklist)}
