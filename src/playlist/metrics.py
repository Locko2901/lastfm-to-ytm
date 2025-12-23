import logging
import time

log = logging.getLogger(__name__)


class _QueryCounter:
    """Track API usage and performance metrics."""

    def __init__(self):
        self.count = 0
        self.session_start = None
        self.operation_counts = {
            "get_playlist": 0,
            "add_playlist_items": 0,
            "remove_playlist_items": 0,
            "get_song": 0,
        }

    def increment(self, operation_type: str = "unknown"):
        if self.session_start is None:
            self.session_start = time.time()

        self.count += 1
        if operation_type in self.operation_counts:
            self.operation_counts[operation_type] += 1

    def reset(self):
        self.count = 0
        self.session_start = time.time()
        self.operation_counts = dict.fromkeys(self.operation_counts, 0)

    def get_count(self):
        return self.count

    def get_session_duration(self):
        if self.session_start is None:
            return 0.0
        return time.time() - self.session_start


_query_counter = _QueryCounter()


def reset_query_counter():
    """Reset the query counter for a new session."""
    _query_counter.reset()


def get_query_count():
    """Return total API query count."""
    return _query_counter.get_count()


def log_playlist_statistics():
    """Log playlist session statistics."""
    if _query_counter.session_start is None:
        return

    session_duration = _query_counter.get_session_duration()
    total_queries = _query_counter.get_count()

    log.info("=== Playlist Session Statistics ===")
    log.info("Total playlist API queries: %d", total_queries)
    log.info("Session duration: %.1f seconds", session_duration)

    if session_duration > 0:
        log.info("Query rate: %.2f queries/second", total_queries / session_duration)

    log.info("Operation breakdown:")
    for op_type, count in _query_counter.operation_counts.items():
        if count > 0:
            percentage = 100.0 * count / total_queries if total_queries > 0 else 0
            log.info("  %s: %d (%.1f%%)", op_type, count, percentage)

    log.info("=====================================")


def get_playlist_statistics():
    """Return playlist session statistics as a dict."""
    return {
        "total_queries": _query_counter.get_count(),
        "session_duration": _query_counter.get_session_duration(),
        "operation_counts": _query_counter.operation_counts.copy(),
        "query_rate": _query_counter.get_count() / _query_counter.get_session_duration() if _query_counter.get_session_duration() > 0 else 0,
    }
