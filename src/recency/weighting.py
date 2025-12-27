import time
from dataclasses import dataclass
from typing import Any

from ..lastfm import Scrobble


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
    """Deduplicate tracks, keeping only the most recent scrobble per track."""
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
) -> list[WeightedTrack]:
    """Aggregate scrobbles to unique tracks ranked by play count + recency.

    Score = play_weight * (normalized plays) + (1-play_weight) * (recency).
    Default: 70% plays, 30% recency.
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

    max_plays = max((int(a["plays"]) for a in agg.values()), default=1)

    items: list[WeightedTrack] = []
    for a in agg.values():
        plays = int(a["plays"])
        ts_latest = int(a["ts_latest"])

        play_score = plays / max_plays

        age_hours = max(0.0, (now - ts_latest) / 3600.0)
        recency_score = 0.5 ** (age_hours / float(half_life_hours)) if half_life_hours > 0 else 1.0

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
    return items
