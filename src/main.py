"""Backward-compatible facade for the workflow entry points.

The implementation now lives in `src.workflows` and `src.observability`. This
module re-exports the public entry points and the legacy private helpers that
external scripts (`run.py`, `run_tags.py`) historically imported from here.
"""

from .observability.failure_log import (
    clear_failure_log as _clear_failure_log,
)
from .observability.failure_log import (
    save_failure_log as _save_failure_log,
)
from .observability.failure_log import (
    save_run_log as _save_run_log,
)
from .observability.history_recording import (
    get_history_db as _get_history_db,
)
from .observability.history_recording import (
    record_sync_error as _record_sync_error,
)
from .observability.history_recording import (
    record_tracks_to_history as _record_tracks_to_history,
)
from .observability.webhooks import fire_webhook as _fire_webhook
from .workflows._common import build_context as _build_context
from .workflows._common import fetch_scrobbles as _fetch_scrobbles
from .workflows.main_sync import run
from .workflows.tag_sync import run_tags

__all__ = [
    "_build_context",
    "_clear_failure_log",
    "_fetch_scrobbles",
    "_fire_webhook",
    "_get_history_db",
    "_record_sync_error",
    "_record_tracks_to_history",
    "_save_failure_log",
    "_save_run_log",
    "run",
    "run_tags",
]
