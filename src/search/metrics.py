import logging
import time
from typing import Any

log = logging.getLogger(__name__)


class _SearchStats:
    """Track search session statistics."""

    def __init__(self) -> None:
        self.total_queries: int = 0
        self.songs_searched: int = 0
        self.early_terminations: int = 0
        self.session_start: float | None = None

    def reset(self) -> None:
        """Reset all counters and start a new session."""
        self.total_queries = 0
        self.songs_searched = 0
        self.early_terminations = 0
        self.session_start = time.time()

    def increment_songs_searched(self) -> None:
        """Increment songs searched counter, starting session if needed."""
        if self.session_start is None:
            self.session_start = time.time()
        self.songs_searched += 1

    def increment_queries(self, count: int) -> None:
        """Add to total query count."""
        self.total_queries += count

    def increment_early_terminations(self) -> None:
        """Increment early termination counter."""
        self.early_terminations += 1

    def get_session_duration(self) -> float:
        """Get duration of current session in seconds."""
        if self.session_start is None:
            return 0.0
        return time.time() - self.session_start

    def get_statistics(self) -> dict[str, Any]:
        """Get all statistics as a dictionary."""
        if self.session_start is None:
            return {
                "total_queries": 0,
                "songs_searched": 0,
                "early_terminations": 0,
                "session_duration": 0,
                "early_termination_rate": 0,
                "search_rate": 0,
                "query_rate": 0,
            }

        session_duration = self.get_session_duration()

        return {
            "total_queries": self.total_queries,
            "songs_searched": self.songs_searched,
            "early_terminations": self.early_terminations,
            "session_duration": session_duration,
            "early_termination_rate": (100.0 * self.early_terminations / self.songs_searched if self.songs_searched > 0 else 0),
            "search_rate": self.songs_searched / session_duration if session_duration > 0 else 0,
            "query_rate": self.total_queries / session_duration if session_duration > 0 else 0,
        }

    def log_statistics(self) -> None:
        """Log session statistics."""
        if self.session_start is None:
            return

        session_duration = self.get_session_duration()

        log.info("=== Search Session Statistics ===")
        log.info("Total songs searched: %d", self.songs_searched)
        log.info("Total API queries: %d", self.total_queries)
        if self.songs_searched > 0:
            log.info(
                "Average queries per song: %.2f",
                self.total_queries / self.songs_searched,
            )
        log.info("Early terminations: %d", self.early_terminations)
        if self.songs_searched > 0:
            log.info(
                "Early termination rate: %.1f%%",
                100.0 * self.early_terminations / self.songs_searched,
            )
        log.info("Session duration: %.1f seconds", session_duration)
        if session_duration > 0:
            log.info(
                "Search rate: %.2f songs/second",
                self.songs_searched / session_duration,
            )
            log.info(
                "Query rate: %.2f queries/second",
                self.total_queries / session_duration,
            )
        log.info("==================================")


_search_stats = _SearchStats()


def increment_songs_searched() -> None:
    """Increment songs searched counter."""
    _search_stats.increment_songs_searched()


def increment_queries(count: int) -> None:
    """Add to total query count."""
    _search_stats.increment_queries(count)


def increment_early_terminations() -> None:
    """Increment early termination counter."""
    _search_stats.increment_early_terminations()


def log_search_statistics() -> None:
    """Log session statistics."""
    _search_stats.log_statistics()


def get_search_statistics() -> dict[str, Any]:
    """Get all statistics as a dictionary."""
    return _search_stats.get_statistics()


def reset_search_statistics() -> None:
    """Reset all counters and start a new session."""
    _search_stats.reset()
