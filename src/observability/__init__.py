"""Observability helpers: failure logs, run logs, history DB recording, webhooks."""

from .failure_log import clear_failure_log, save_failure_log, save_run_log
from .history_recording import get_history_db, record_near_misses_to_history, record_sync_error, record_tracks_to_history
from .http_status import describe_sync_error, extract_http_status, is_rate_limited, is_retryable
from .webhooks import fire_webhook

__all__ = [
    "clear_failure_log",
    "describe_sync_error",
    "extract_http_status",
    "fire_webhook",
    "get_history_db",
    "is_rate_limited",
    "is_retryable",
    "record_near_misses_to_history",
    "record_sync_error",
    "record_tracks_to_history",
    "save_failure_log",
    "save_run_log",
]
