import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..lastfm import Scrobble

# Exponential half-life decay base: score halves every ``half_life_hours``.
_DECAY_BASE = 0.5
# Seconds in one hour, used to convert scrobble age to hours.
_SECONDS_PER_HOUR = 3600.0
# Number of top tracks to emit in the debug timestamp dump.
_DEBUG_TOP_N = 50
# Max characters of a track title shown in the debug dump.
_DEBUG_TITLE_WIDTH = 25

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class WeightedTrack:
    """A track with aggregated play count and recency score."""

    artist: str
    track: str
    album: str
    ts: int
    plays: int
    score: float


def dedupe_keep_latest(tracks: list[Scrobble]) -> list[Scrobble]:
    """Keep most recent scrobble per track."""
    latest: dict[tuple[str, str], Scrobble] = {}
    for tr in tracks:
        key = (tr.artist.lower(), tr.track.lower())
        prev = latest.get(key)
        if prev is None or tr.ts > prev.ts:
            latest[key] = tr
    return sorted(latest.values(), key=lambda x: x.ts, reverse=True)


def collapse_recency_weighted(
    recents: list[Scrobble],
    half_life_hours: float = 24.0,
    play_weight: float = 0.7,
    min_plays: int = 1,
) -> list[WeightedTrack]:
    """Aggregate scrobbles to unique tracks ranked by play count + recency.

    Tracks with fewer than ``min_plays`` scrobbles within the fetched window
    are filtered out before scoring.
    """
    now = time.time()
    agg: dict[tuple[str, str], dict[str, Any]] = {}

    for t in recents:
        key = (t.artist.lower(), t.track.lower())
        if key not in agg:
            agg[key] = {
                "artist": t.artist,
                "track": t.track,
                "album": t.album,
                "ts_latest": t.ts,
                "plays": 1,
            }
        else:
            a = agg[key]
            a["plays"] = int(a["plays"]) + 1
            if t.ts > int(a["ts_latest"]):
                a["ts_latest"] = t.ts
                if t.album:
                    a["album"] = t.album

    if min_plays > 1:
        before = len(agg)
        agg = {k: v for k, v in agg.items() if int(v["plays"]) >= min_plays}
        log.info("min_plays=%d filter: %d/%d tracks kept", min_plays, len(agg), before)

    max_plays = max((int(a["plays"]) for a in agg.values()), default=1)

    items: list[WeightedTrack] = []
    for a in agg.values():
        plays = int(a["plays"])
        ts_latest = int(a["ts_latest"])

        play_score = plays / max_plays

        age_hours = max(0.0, (now - ts_latest) / _SECONDS_PER_HOUR)
        recency_score = _DECAY_BASE ** (age_hours / float(half_life_hours)) if half_life_hours > 0 else 1.0

        recency_weight = 1.0 - play_weight
        score = play_weight * play_score + recency_weight * recency_score

        items.append(
            WeightedTrack(
                artist=str(a["artist"]),
                track=str(a["track"]),
                album=str(a.get("album", "")),
                ts=ts_latest,
                plays=plays,
                score=score,
            )
        )

    items.sort(key=lambda x: (-x.score, -x.ts, -x.plays))

    log.debug(
        "=== Top %d track timestamps (play_weight=%.2f, half_life=%.1fh, max_plays=%d) ===", _DEBUG_TOP_N, play_weight, half_life_hours, max_plays
    )
    for i, wt in enumerate(items[:_DEBUG_TOP_N], 1):
        age_hours = (now - wt.ts) / _SECONDS_PER_HOUR
        recency_score = _DECAY_BASE ** (age_hours / float(half_life_hours)) if half_life_hours > 0 else 1.0
        play_score = wt.plays / max_plays
        dt = datetime.fromtimestamp(wt.ts, tz=UTC)
        log.debug(
            "  %2d. %-25s | plays=%2d (%.2f) | last=%s (%.1fh ago, rec=%.3f) | score=%.4f",
            i,
            wt.track[:_DEBUG_TITLE_WIDTH],
            wt.plays,
            play_score,
            dt.strftime("%m-%d %H:%M"),
            age_hours,
            recency_score,
            wt.score,
        )

    return items


def weight_history_tracks(
    records: list[tuple[str, str, str, int, int]],
    half_life_hours: float = 48.0,
    play_weight: float = 0.7,
    min_plays: int = 1,
) -> list[WeightedTrack]:
    """Score pre-aggregated lifetime scrobble history into ranked tracks.

    ``records`` are ``(artist, track, album, plays, last_played_uts)`` tuples
    sourced from the local Last.fm database. Unlike :func:`collapse_recency_weighted`
    (which counts plays within a fetch window), this uses the lifetime play count
    and decays recency from the last time the track was played.
    """
    now = time.time()
    if min_plays > 1:
        records = [r for r in records if r[3] >= min_plays]

    max_plays = max((r[3] for r in records), default=1)

    items: list[WeightedTrack] = []
    for artist, track, album, plays, last_uts in records:
        play_score = plays / max_plays

        age_hours = max(0.0, (now - last_uts) / _SECONDS_PER_HOUR) if last_uts > 0 else float("inf")
        if half_life_hours > 0 and age_hours != float("inf"):
            recency_score = _DECAY_BASE ** (age_hours / float(half_life_hours))
        elif age_hours == float("inf"):
            recency_score = 0.0
        else:
            recency_score = 1.0

        recency_weight = 1.0 - play_weight
        score = play_weight * play_score + recency_weight * recency_score

        items.append(
            WeightedTrack(
                artist=artist,
                track=track,
                album=album,
                ts=last_uts,
                plays=plays,
                score=score,
            )
        )

    items.sort(key=lambda x: (-x.score, -x.ts, -x.plays))

    log.info(
        "Scored %d tracks from local Last.fm history (play_weight=%.2f, half_life=%.1fh, max_plays=%d)",
        len(items),
        play_weight,
        half_life_hours,
        max_plays,
    )

    return items
