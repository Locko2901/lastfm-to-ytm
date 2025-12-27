from __future__ import annotations

import fcntl
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generic, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


class CacheMetrics:
    """Track cache performance metrics."""

    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.writes = 0

    def record_hit(self) -> None:
        """Record a cache hit."""
        self.hits += 1

    def record_miss(self) -> None:
        """Record a cache miss."""
        self.misses += 1

    def record_write(self) -> None:
        """Record a cache write."""
        self.writes += 1

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with hit/miss rates and counts
        """
        total_reads = self.hits + self.misses
        hit_rate = (self.hits / total_reads * 100) if total_reads > 0 else 0.0

        return {
            "hits": self.hits,
            "misses": self.misses,
            "writes": self.writes,
            "total_reads": total_reads,
            "hit_rate_percent": hit_rate,
        }

    def log_stats(self, cache_name: str) -> None:
        """Log cache statistics.

        Args:
            cache_name: Name of the cache for logging
        """
        stats = self.get_stats()
        if stats["total_reads"] > 0:
            log.info(
                "%s cache stats - Hits: %d, Misses: %d, Hit rate: %.1f%%, Writes: %d",
                cache_name,
                stats["hits"],
                stats["misses"],
                stats["hit_rate_percent"],
                stats["writes"],
            )

    def reset(self) -> None:
        """Reset all counters to zero."""
        self.hits = 0
        self.misses = 0
        self.writes = 0


class JSONCache(Generic[T]):
    """Base class for JSON-based persistent caches with atomic writes and file locking."""

    def __init__(self, cache_file: str, enable_locking: bool = True):
        """Initialize cache with a file path.

        Args:
            cache_file: Path to cache file relative to project root
            enable_locking: Enable file locking for multi-process safety
        """
        self.cache_file = Path(cache_file)
        self.enable_locking = enable_locking
        self._cache: dict[str, Any] = {}
        self._metrics = CacheMetrics()

    @contextmanager
    def _file_lock(self, mode: str = "r"):
        """Context manager for file locking to prevent concurrent access.

        Args:
            mode: File open mode ('r' for read, 'w' for write)

        Yields:
            File handle with acquired lock
        """
        if not self.enable_locking:
            if (mode == "r" and self.cache_file.exists()) or mode == "w":
                with self.cache_file.open(mode) as f:
                    yield f
            else:
                yield None
            return

        self.cache_file.parent.mkdir(parents=True, exist_ok=True)

        if not self.cache_file.exists() and mode == "r":
            yield None
            return

        lock_mode = fcntl.LOCK_SH if mode == "r" else fcntl.LOCK_EX

        try:
            with self.cache_file.open(mode if mode == "w" else "r+") as f:
                fcntl.flock(f.fileno(), lock_mode)
                try:
                    yield f
                finally:
                    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except OSError as e:
            log.warning("Failed to acquire lock on %s: %s", self.cache_file.name, e)
            yield None

    def _load(self) -> None:
        """Load cache from disk with file locking."""
        with self._file_lock("r") as f:
            if f is None:
                log.debug(
                    "No existing cache found at %s, starting fresh",
                    self.cache_file.name,
                )
                self._cache = {}
                return

            try:
                self._cache = json.load(f)
                log.debug(
                    "Loaded cache from %s with %d entries",
                    self.cache_file.name,
                    len(self._cache),
                )
            except json.JSONDecodeError as e:
                log.warning("Corrupted cache file %s, resetting: %s", self.cache_file.name, e)
                self._cache = {}
            except (PermissionError, OSError) as e:
                log.error("Cannot read cache file %s: %s", self.cache_file.name, e)
                self._cache = {}

    def _save(self) -> None:
        """Save cache to disk atomically with file locking."""
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            temp_file = self.cache_file.with_suffix(".tmp")

            with temp_file.open("w") as f:
                if self.enable_locking:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                try:
                    json.dump(self._cache, f, indent=2)
                finally:
                    if self.enable_locking:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            temp_file.replace(self.cache_file)
            log.debug(
                "Saved cache to %s with %d entries",
                self.cache_file.name,
                len(self._cache),
            )
            self._metrics.record_write()
        except (PermissionError, OSError) as e:
            log.error("Cannot write cache file %s: %s", self.cache_file.name, e)
            raise
        except Exception as e:
            log.error("Unexpected error saving cache to %s: %s", self.cache_file.name, e)

    def clear(self) -> None:
        """Clear all cache entries."""
        log.info("Clearing cache %s", self.cache_file.name)
        self._cache = {}
        self._save()

    def size(self) -> int:
        """Return number of entries in cache."""
        return len(self._cache)

    def get_metrics(self) -> CacheMetrics:
        """Return cache metrics tracker."""
        return self._metrics

    def log_metrics(self, cache_name: str) -> None:
        """Log cache performance metrics.

        Args:
            cache_name: Name of the cache for logging
        """
        self._metrics.log_stats(cache_name)
