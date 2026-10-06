"""Decide whether a detected play is already on Last.fm.

A duplicate is a recent scrobble (or the now playing track) of the same track
(see ``matching``) within the play's window; each scrobble covers at most one
play. Another version or artist with the same title is kept as a near miss.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .matching import ARTIST_DIFFERS, MATCH, VERSION_DIFFERS, TrackKey, compare, track_key

DEFAULT_DURATION_SECONDS = 240


def window_seconds(duration: int | None, gap: float) -> int:
    """Half-width of the duplicate window: the track's duration plus the poll gap."""
    return round((duration or DEFAULT_DURATION_SECONDS) + max(0.0, gap))


@dataclass(frozen=True, slots=True)
class Candidate:
    """A scrobble already on Last.fm, or the now playing track (timestamped at the poll)."""

    artist: str
    track: str
    album: str
    timestamp: int
    now_playing: bool = False

    @property
    def key(self) -> TrackKey:
        """Comparison key of this scrobble."""
        return track_key(self.artist, self.track)

    def to_dict(self) -> dict[str, object]:
        """Plain form for the decision log."""
        return {
            "artist": self.artist,
            "track": self.track,
            "album": self.album,
            "timestamp": self.timestamp,
            "now_playing": self.now_playing,
        }


@dataclass(frozen=True, slots=True)
class DedupResult:
    """Which candidate covers the play, if any, and the closest near miss."""

    duplicate: int | None = None
    near_miss: int | None = None
    near_miss_reason: str = ""


def find_duplicate(key: TrackKey, timestamp: int, window: int, candidates: Sequence[Candidate], used: set[int]) -> DedupResult:
    """Return the closest unused candidate that covers the play, plus the closest near miss."""
    best: tuple[int, int] | None = None
    near: tuple[int, int, str] | None = None
    for index, candidate in enumerate(candidates):
        if index in used:
            continue
        distance = abs(candidate.timestamp - timestamp)
        if distance > window:
            continue
        verdict = compare(key, candidate.key)
        if verdict == MATCH:
            if best is None or distance < best[1]:
                best = (index, distance)
        elif verdict in (VERSION_DIFFERS, ARTIST_DIFFERS) and (near is None or distance < near[1]):
            near = (index, distance, verdict)
    return DedupResult(
        duplicate=best[0] if best else None,
        near_miss=near[0] if near else None,
        near_miss_reason=near[2] if near else "",
    )
