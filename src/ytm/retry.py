"""Retry YouTube Music calls with exponential backoff, the project's standard for flaky API reads and writes."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from ytmusicapi.exceptions import YTMusicServerError

from ..observability.http_status import extract_http_status, is_retryable

log = logging.getLogger(__name__)


def retry_with_backoff(
    func: Callable[..., Any], *args: Any, max_retries: int = 3, initial_delay: float = 1.0, operation: str = "operation", **kwargs: Any
) -> Any:
    """Retry with exponential backoff on rate limit errors; 400 and 409 fail at once, since they never succeed."""
    delay = initial_delay
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (RuntimeError, ValueError, OSError, YTMusicServerError) as e:
            last_exception = e
            error_msg = str(e)
            status = extract_http_status(error_msg)

            if status in (400, 409):
                raise

            if is_retryable(error_msg) and attempt < max_retries - 1:
                log.warning(
                    "%s: %s (retry %d/%d in %.1fs)",
                    operation,
                    f"HTTP {status}" if status else "transient error",
                    attempt + 1,
                    max_retries - 1,
                    delay,
                )
                time.sleep(delay)
                delay *= 2
            else:
                raise

    assert last_exception is not None
    raise last_exception
