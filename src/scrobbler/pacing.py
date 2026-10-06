"""Adaptive polling: the fastest interval while the history changes, the idle one after 30 quiet minutes, slower after errors.

The scheduler ticks at the fastest interval; each tick polls only when
``poll_due`` says so.
"""

from __future__ import annotations

FAST = "fast"
IDLE = "idle"
BACKOFF = "backoff"

IDLE_AFTER_SECONDS = 30 * 60
IDLE_INTERVAL_SECONDS = 10 * 60
MAX_ERROR_INTERVAL_SECONDS = 30 * 60
TICK_TOLERANCE_SECONDS = 5


def pace(fastest: float, now: float, last_change: float | None, errors: int, *, idle: float = IDLE_INTERVAL_SECONDS) -> tuple[str, float]:
    """Return the current pace and its interval in seconds; each failed read in a row doubles the interval, up to 30 minutes."""
    if errors > 0:
        return BACKOFF, max(fastest, min(MAX_ERROR_INTERVAL_SECONDS, fastest * 2**errors))
    if last_change is None or now - last_change > IDLE_AFTER_SECONDS:
        return IDLE, max(fastest, idle)
    return FAST, fastest


def poll_due(
    fastest: float, now: float, last_attempt: float | None, last_change: float | None, errors: int, *, idle: float = IDLE_INTERVAL_SECONDS
) -> bool:
    """True when a scheduler tick at ``now`` should poll."""
    if last_attempt is None:
        return True
    _pace, interval = pace(fastest, now, last_change, errors, idle=idle)
    return now - last_attempt >= interval - TICK_TOLERANCE_SECONDS


def next_poll_at(
    next_tick: float,
    fastest: float,
    last_attempt: float | None,
    last_change: float | None,
    errors: int,
    *,
    idle: float = IDLE_INTERVAL_SECONDS,
) -> float:
    """The first scheduler tick, from ``next_tick`` on, at which a poll is due."""
    tick = next_tick
    for _ in range(int(max(idle, MAX_ERROR_INTERVAL_SECONDS) // max(fastest, 1.0)) + 2):
        if poll_due(fastest, tick, last_attempt, last_change, errors, idle=idle):
            return tick
        tick += fastest
    return tick
