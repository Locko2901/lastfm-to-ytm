"""Facade for the workflow entry points.

The implementation lives in `src.workflows` and `src.observability`. This
module re-exports the public entry points (`run`, `run_tags`). For observability
helpers, import directly from `src.observability`.
"""

from .workflows.main_sync import run
from .workflows.tag_sync import run_tags

__all__ = [
    "run",
    "run_tags",
]
