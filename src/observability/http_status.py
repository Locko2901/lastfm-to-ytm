r"""Robust HTTP status classification for upstream (YTM / Last.fm) errors.

ytmusicapi surfaces backend failures as ``YTMusicServerError`` with a message
formatted like ``"Server returned HTTP 403: Forbidden.\n<detail>"``. The status
code is only available as text, so detection must parse it precisely rather than
testing for a bare ``"403"`` substring (which also matches video IDs, counts,
timestamps and OAuth content dumps).
"""

from __future__ import annotations

import re

# Matches "HTTP 403", "HTTP/403", "HTTP403" - but not bare digits or "https".
_HTTP_STATUS_RE = re.compile(r"HTTP[/ ]?(\d{3})", re.IGNORECASE)

# Rate-limit / transient server errors worth retrying with backoff.
RETRYABLE_STATUSES = frozenset({403, 408, 429, 500, 502, 503, 504})
# Client errors that will never succeed on retry.
TERMINAL_STATUSES = frozenset({400, 409})
# Statuses that specifically indicate throttling.
RATE_LIMIT_STATUSES = frozenset({403, 429})


def extract_http_status(error_msg: str) -> int | None:
    """Return the HTTP status code embedded in an error message, if any."""
    match = _HTTP_STATUS_RE.search(error_msg)
    return int(match.group(1)) if match else None


def is_retryable(error_msg: str) -> bool:
    """Whether an upstream error is a transient/rate-limit failure worth retrying."""
    status = extract_http_status(error_msg)
    if status is not None:
        return status in RETRYABLE_STATUSES
    return "Expecting value" in error_msg


def is_rate_limited(error_msg: str) -> bool:
    """Whether an upstream error indicates rate limiting / throttling."""
    if extract_http_status(error_msg) in RATE_LIMIT_STATUSES:
        return True
    return "rate limit" in error_msg.lower()


def describe_sync_error(error_msg: str) -> str:
    """Return a concise, human-readable summary of an upstream sync error.

    Classification is based on the parsed HTTP status code rather than fragile
    substring matching, so a reworded upstream message still maps to the right
    category. Falls back to the raw message for unrecognised errors.
    """
    status = extract_http_status(error_msg)
    if status == 401:
        return "HTTP 401 - Unauthorized"
    if status == 403:
        return "HTTP 403 - rate limit or auth expired"
    if status is not None:
        return f"HTTP {status}"
    if "Expecting value" in error_msg:
        return "Invalid API response (likely rate limited)"
    return error_msg
