"""Real-time scrobbler activity: history plays from while another scrobbler was active are left to it.

The evidence is Last.fm's now playing at each poll and the scrobbles that are
not the add-on's own; docs/scrobbler.md explains the active periods and their
edges.
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable
from dataclasses import dataclass

REALTIME_GAP_SECONDS = 10 * 60
CLOCK_SLACK_SECONDS = 30
NOW_PLAYING_MEMORY_SECONDS = 30 * 24 * 3600


@dataclass(frozen=True, slots=True)
class Period:
    """A stretch of real-time scrobbler activity and the number of evidence points in it."""

    start: float
    end: float
    points: int


def active_periods(sightings: Iterable[tuple[float, bool]], scrobbles: Iterable[float], gap: float = REALTIME_GAP_SECONDS) -> list[Period]:
    """Chain the evidence into active periods, oldest first.

    ``sightings`` are ``(poll time, playing)``: whether the real-time scrobbler
    showed the song on top of the history as now playing at that poll.
    """
    spans: list[tuple[float, float]] = []
    idle: list[float] = []
    for at, playing in sightings:
        if playing:
            spans.append((at, at))
        else:
            idle.append(at)
    spans += [(t - CLOCK_SLACK_SECONDS, t + CLOCK_SLACK_SECONDS) for t in scrobbles]
    idle.sort()
    periods: list[Period] = []
    for start, end in sorted(spans):
        if periods:
            last = periods[-1]
            seen_idle = bisect.bisect_right(idle, last.end) < bisect.bisect_left(idle, start)
            if start - last.end <= gap and not seen_idle:
                periods[-1] = Period(last.start, max(last.end, end), last.points + 1)
                continue
        periods.append(Period(start, end, 1))
    return periods


def usable_sightings(sightings: Iterable[tuple[float, bool]], reports_now_playing: bool) -> list[tuple[float, bool]]:
    """The sightings to use: all of them once a real-time scrobbler was seen showing now playing, else none.

    Without such a sighting (in the last ``NOW_PLAYING_MEMORY_SECONDS``) the
    real-time scrobbler may simply not send now playing, so a poll that saw
    nothing says nothing about whether it was idle.
    """
    return list(sightings) if reports_now_playing else []


def active_during(periods: Iterable[Period], window_start: float, window_end: float) -> Period | None:
    """The active period that overlaps the start window ``(window_start, window_end]``, if any."""
    return next((p for p in periods if p.end > window_start and p.start <= window_end), None)
