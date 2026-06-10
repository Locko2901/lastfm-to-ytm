from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import JSONCache

log = logging.getLogger(__name__)


class TagCache(JSONCache[Any]):
    """Persistent cache for artist/title -> Last.fm tag mappings."""

    def __init__(self, cache_file: str, ttl_days: int = 90):
        cache_path = Path(cache_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(cache_file)
        self.ttl_days = ttl_days
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

            if self.ttl_days > 0:
                cutoff = now - timedelta(days=self.ttl_days)
                if timestamp < cutoff:
                    expired_keys.append(key)

        if expired_keys:
            for key in expired_keys:
                del self._cache[key]
            log.info("Cleaned %d expired tag cache entries", len(expired_keys))
            self._save()

    def _make_key(self, artist: str, title: str) -> str:
        return f"{artist.lower()}|{title.lower()}"

    def get(self, artist: str, title: str) -> list[dict[str, Any]] | None:
        """Get tags or None if expired."""
        key = self._make_key(artist, title)
        entry = self._cache.get(key)

        if not entry:
            self._metrics.record_miss()
            return None

        timestamp_str = entry.get("timestamp")
        if timestamp_str and self.ttl_days > 0:
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
                cutoff = datetime.now(UTC) - timedelta(days=self.ttl_days)
                if timestamp < cutoff:
                    self._metrics.record_miss()
                    return None
            except Exception:
                self._metrics.record_miss()
                return None

        self._metrics.record_hit()
        return list(entry.get("tags", []))

    def set(self, artist: str, title: str, tags: list[dict[str, Any]]) -> None:
        """Cache tags for a track."""
        key = self._make_key(artist, title)
        self._cache[key] = {
            "artist": artist,
            "title": title,
            "tags": tags,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self._save()

    def items(self) -> list[tuple[str, dict[str, Any]]]:
        """Return all cache entries."""
        return list(self._cache.items())

    def delete_by_track(self, artist: str, title: str) -> bool:
        """Delete tag cache entry."""
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

    def stats(self) -> dict[str, int]:
        """Get cache statistics."""
        total = len(self._cache)
        with_tags = sum(1 for entry in self._cache.values() if entry.get("tags"))
        return {"total": total, "with_tags": with_tags, "empty": total - with_tags}


class TagOverrides(JSONCache[Any]):
    """Manual tag overrides for tracks where Last.fm tags are missing or wrong."""

    def __init__(self, overrides_file: str):
        cache_path = Path(overrides_file)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        super().__init__(overrides_file)
        self._load()
        self._ensure_sections()

    def _ensure_sections(self) -> None:
        if "_overrides" not in self._cache:
            self._cache["_overrides"] = {}

    def _make_key(self, artist: str, title: str) -> str:
        return f"{artist.lower()}|{title.lower()}"

    def get(self, artist: str, title: str) -> tuple[list[dict[str, Any]], str] | None:
        """Get tag override for a track. Returns (tags, mode) or None."""
        key = self._make_key(artist, title)
        entry = self._cache.get("_overrides", {}).get(key)
        if not entry:
            return None

        raw_tags = entry.get("tags", [])
        mode = entry.get("mode", "add")
        tags = [{"name": t.lower(), "count": 100, "source": "override"} for t in raw_tags if isinstance(t, str)]

        if tags:
            self._metrics.record_hit()
            return tags, mode

        return None

    def apply(self, artist: str, title: str, api_tags: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Apply override to API-fetched tags, returning the final tag list."""
        result = self.get(artist, title)
        if result is None:
            return api_tags

        override_tags, mode = result

        if mode == "replace":
            log.debug("Tag override (replace): %s - %s -> %d tags", artist, title, len(override_tags))
            return override_tags

        existing_names = {t["name"] for t in override_tags}
        merged = list(override_tags)
        merged.extend(t for t in api_tags if t["name"] not in existing_names)
        log.debug("Tag override (add): %s - %s -> %d tags (+%d custom)", artist, title, len(merged), len(override_tags))
        return merged

    def set(self, artist: str, title: str, tags: list[str], mode: str = "add", reason: str = "") -> None:
        """Add a tag override."""
        key = self._make_key(artist, title)
        overrides = self._cache.setdefault("_overrides", {})
        overrides[key] = {
            "artist": artist,
            "title": title,
            "tags": tags,
            "mode": mode,
            "reason": reason,
        }
        self._save()
        self._metrics.record_write()

    def remove(self, artist: str, title: str) -> bool:
        """Remove a tag override. Returns True if removed."""
        key = self._make_key(artist, title)
        overrides = self._cache.get("_overrides", {})
        if key in overrides:
            del overrides[key]
            self._save()
            return True
        return False

    def items(self) -> list[tuple[str, dict[str, Any]]]:
        """Return all override entries."""
        return list(self._cache.get("_overrides", {}).items())

    def stats(self) -> dict[str, int]:
        """Get override statistics."""
        overrides = self._cache.get("_overrides", {})
        add_count = sum(1 for e in overrides.values() if e.get("mode", "add") == "add")
        replace_count = sum(1 for e in overrides.values() if e.get("mode", "add") == "replace")
        return {"total": len(overrides), "add": add_count, "replace": replace_count}
