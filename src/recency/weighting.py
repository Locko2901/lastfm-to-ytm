import logging
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..lastfm import Scrobble

# Exponential half-life decay base: score halves every ``half_life_hours``.
_DECAY_BASE = 0.5
# Seconds in one hour, used to convert scrobble age to hours.
_SECONDS_PER_HOUR = 3600.0
# Seconds in one day, used to convert play spans to days for velocity.
_SECONDS_PER_DAY = 86400.0
# Number of top tracks to emit in the debug timestamp dump.
_DEBUG_TOP_N = 50
# Max characters of a track title shown in the debug dump.
_DEBUG_TITLE_WIDTH = 25

log = logging.getLogger(__name__)


def _compute_play_scores(plays: list[float], normalization: str) -> list[float]:
    """Normalize raw play counts into ``[0, 1]`` scores.

    ``linear`` (default) divides by the maximum, matching the original
    behaviour. ``log`` applies ``log1p`` before dividing to compress the
    influence of a few very-high-play outliers. ``rank`` ignores absolute
    magnitude entirely and scores each track by its (tie-averaged) percentile
    position within the set.
    """
    n = len(plays)
    if n == 0:
        return []

    if normalization == "rank":
        order = sorted(range(n), key=lambda i: plays[i])
        scores = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and plays[order[j + 1]] == plays[order[i]]:
                j += 1
            avg_rank = (i + 1 + j + 1) / 2.0
            for k in range(i, j + 1):
                scores[order[k]] = avg_rank / n
            i = j + 1
        return scores

    max_plays = max(plays) or 1.0
    if normalization == "log":
        denom = math.log1p(max_plays) or 1.0
        return [math.log1p(p) / denom for p in plays]

    return [p / max_plays for p in plays]


def _normalize_max(values: list[float]) -> list[float]:
    """Scale values to ``[0, 1]`` by dividing by the maximum (0 when empty)."""
    if not values:
        return []
    peak = max(values) or 1.0
    return [v / peak for v in values]


def _resolve_zone(timezone: str) -> ZoneInfo:
    """Return a ``ZoneInfo`` for ``timezone``, falling back to UTC."""
    try:
        return ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError):
        log.warning("Unknown session timezone %r; falling back to UTC", timezone)
        return ZoneInfo("UTC")


def _in_session(hour: int, start: int, end: int) -> bool:
    """Return whether ``hour`` falls in the half-open window ``[start, end)``.

    Supports wrap-around windows (e.g. ``start=22, end=4`` for late nights).
    A window where ``start == end`` covers the whole day.
    """
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


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
    normalization: str = "linear",
    velocity_weight: float = 0.0,
    session_weighting: bool = False,
    session_start: int = 9,
    session_end: int = 23,
    session_timezone: str = "UTC",
    session_multiplier: float = 1.5,
) -> list[WeightedTrack]:
    """Aggregate scrobbles to unique tracks ranked by play count + recency.

    Tracks with fewer than ``min_plays`` scrobbles within the fetched window
    are filtered out before scoring.

    ``normalization`` selects how raw play counts are scaled (``linear``,
    ``log`` or ``rank``). ``velocity_weight`` (0 = off) blends in a
    plays-per-day trending signal. ``session_weighting`` boosts plays that
    happened within the local-time window ``[session_start, session_end)`` by
    ``session_multiplier`` before scoring.
    """
    now = time.time()
    agg: dict[tuple[str, str], dict[str, Any]] = {}

    session_zone = _resolve_zone(session_timezone) if session_weighting else None

    for t in recents:
        key = (t.artist.lower(), t.track.lower())
        weight = 1.0
        if session_zone is not None:
            hour = datetime.fromtimestamp(t.ts, tz=session_zone).hour
            if _in_session(hour, session_start, session_end):
                weight = session_multiplier
        if key not in agg:
            agg[key] = {
                "artist": t.artist,
                "track": t.track,
                "album": t.album,
                "ts_latest": t.ts,
                "ts_earliest": t.ts,
                "plays": 1,
                "eff_plays": weight,
            }
        else:
            a = agg[key]
            a["plays"] = int(a["plays"]) + 1
            a["eff_plays"] = float(a["eff_plays"]) + weight
            if t.ts > int(a["ts_latest"]):
                a["ts_latest"] = t.ts
                if t.album:
                    a["album"] = t.album
            if t.ts < int(a["ts_earliest"]):
                a["ts_earliest"] = t.ts

    if min_plays > 1:
        before = len(agg)
        agg = {k: v for k, v in agg.items() if int(v["plays"]) >= min_plays}
        log.info("min_plays=%d filter: %d/%d tracks kept", min_plays, len(agg), before)

    aggs = list(agg.values())
    if not aggs:
        return []

    play_scores = _compute_play_scores([float(a["eff_plays"]) for a in aggs], normalization)

    use_velocity = velocity_weight > 0.0
    if use_velocity:
        velocity_raw = [int(a["plays"]) / max((int(a["ts_latest"]) - int(a["ts_earliest"])) / _SECONDS_PER_DAY, 1.0) for a in aggs]
        velocity_scores = _normalize_max(velocity_raw)
    else:
        velocity_scores = [0.0] * len(aggs)

    recency_weight = 1.0 - play_weight
    items: list[WeightedTrack] = []
    for a, play_score, velocity_score in zip(aggs, play_scores, velocity_scores, strict=True):
        ts_latest = int(a["ts_latest"])
        age_hours = max(0.0, (now - ts_latest) / _SECONDS_PER_HOUR)
        recency_score = _DECAY_BASE ** (age_hours / float(half_life_hours)) if half_life_hours > 0 else 1.0

        base_score = play_weight * play_score + recency_weight * recency_score
        score = (1.0 - velocity_weight) * base_score + velocity_weight * velocity_score if use_velocity else base_score

        items.append(
            WeightedTrack(
                artist=str(a["artist"]),
                track=str(a["track"]),
                album=str(a.get("album", "")),
                ts=ts_latest,
                plays=int(a["plays"]),
                score=score,
            )
        )

    items.sort(key=lambda x: (-x.score, -x.ts, -x.plays))

    max_plays = max((int(a["plays"]) for a in aggs), default=1)
    log.debug(
        "=== Top %d track timestamps (norm=%s, play_weight=%.2f, vel_weight=%.2f, half_life=%.1fh, max_plays=%d) ===",
        _DEBUG_TOP_N,
        normalization,
        play_weight,
        velocity_weight,
        half_life_hours,
        max_plays,
    )
    for i, wt in enumerate(items[:_DEBUG_TOP_N], 1):
        age_hours = (now - wt.ts) / _SECONDS_PER_HOUR
        recency_score = _DECAY_BASE ** (age_hours / float(half_life_hours)) if half_life_hours > 0 else 1.0
        dt = datetime.fromtimestamp(wt.ts, tz=UTC)
        log.debug(
            "  %2d. %-25s | plays=%2d | last=%s (%.1fh ago, rec=%.3f) | score=%.4f",
            i,
            wt.track[:_DEBUG_TITLE_WIDTH],
            wt.plays,
            dt.strftime("%m-%d %H:%M"),
            age_hours,
            recency_score,
            wt.score,
        )

    return items


def weight_history_tracks(
    records: list[tuple[str, str, str, int, int, int]],
    half_life_hours: float = 48.0,
    play_weight: float = 0.7,
    min_plays: int = 1,
    normalization: str = "linear",
    velocity_weight: float = 0.0,
) -> list[WeightedTrack]:
    """Score pre-aggregated lifetime scrobble history into ranked tracks.

    ``records`` are ``(artist, track, album, plays, first_played_uts,
    last_played_uts)`` tuples sourced from the local Last.fm database. Unlike
    :func:`collapse_recency_weighted` (which counts plays within a fetch
    window), this uses the lifetime play count and decays recency from the last
    time the track was played.

    ``normalization`` and ``velocity_weight`` behave as in
    :func:`collapse_recency_weighted`; velocity is derived from the span
    between ``first_played_uts`` and ``last_played_uts``. Session weighting is
    unavailable here because per-scrobble timestamps are not retained.
    """
    now = time.time()
    if min_plays > 1:
        records = [r for r in records if r[3] >= min_plays]

    if not records:
        return []

    play_scores = _compute_play_scores([float(r[3]) for r in records], normalization)

    use_velocity = velocity_weight > 0.0
    if use_velocity:
        velocity_raw = [r[3] / max((r[5] - r[4]) / _SECONDS_PER_DAY, 1.0) if r[4] > 0 and r[5] > 0 else 0.0 for r in records]
        velocity_scores = _normalize_max(velocity_raw)
    else:
        velocity_scores = [0.0] * len(records)

    recency_weight = 1.0 - play_weight
    items: list[WeightedTrack] = []
    for (artist, track, album, plays, _first_uts, last_uts), play_score, velocity_score in zip(records, play_scores, velocity_scores, strict=True):
        age_hours = max(0.0, (now - last_uts) / _SECONDS_PER_HOUR) if last_uts > 0 else float("inf")
        if half_life_hours > 0 and age_hours != float("inf"):
            recency_score = _DECAY_BASE ** (age_hours / float(half_life_hours))
        elif age_hours == float("inf"):
            recency_score = 0.0
        else:
            recency_score = 1.0

        base_score = play_weight * play_score + recency_weight * recency_score
        score = (1.0 - velocity_weight) * base_score + velocity_weight * velocity_score if use_velocity else base_score

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

    max_plays = max((r[3] for r in records), default=1)
    log.info(
        "Scored %d tracks from local Last.fm history (norm=%s, play_weight=%.2f, vel_weight=%.2f, half_life=%.1fh, max_plays=%d)",
        len(items),
        normalization,
        play_weight,
        velocity_weight,
        half_life_hours,
        max_plays,
    )

    return items
