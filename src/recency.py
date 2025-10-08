from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .lastfm import Scrobble


@dataclass(frozen=True)
class WeightedTrack:
    artist: str
    track: str
    album: str
    ts: int
    plays: int
    score: float


def dedupe_keep_latest(tracks: List[Scrobble]) -> List[Scrobble]:
    """
    Keep only the latest play per (artist, track), sorted by ts desc.
    """
    latest: Dict[Tuple[str, str], Scrobble] = {}
    for tr in tracks:
        key = (tr.artist.lower(), tr.track.lower())
        prev = latest.get(key)
        if prev is None or tr.ts > prev.ts:
            latest[key] = tr
    return sorted(latest.values(), key=lambda x: x.ts, reverse=True)


def collapse_recency_weighted(
    recents: List[Scrobble],
    half_life_hours: float = 24.0,
    max_unique: Optional[int] = None,
) -> List[WeightedTrack]:
    """
    Aggregate scrobbles to unique tracks ranked by recency-weighted score.
    Each play weights 0.5 ** (age_hours / half_life_hours); sum per track.
    """
    now = time.time()
    agg: Dict[Tuple[str, str], Dict[str, object]] = {}

    for t in recents:
        key = (t.artist.lower(), t.track.lower())
        age_hours = max(0.0, (now - t.ts) / 3600.0)
        w = 0.5 ** (age_hours / float(half_life_hours)) if half_life_hours > 0 else 1.0

        if key not in agg:
            agg[key] = {
                "artist": t.artist,
                "track": t.track,
                "album": t.album,
                "ts_latest": t.ts,
                "plays": 1,
                "score": w,
            }
        else:
            a = agg[key]
            a["plays"] = int(a["plays"]) + 1
            a["score"] = float(a["score"]) + w
            if t.ts > int(a["ts_latest"]):
                a["ts_latest"] = t.ts
                if t.album:
                    a["album"] = t.album

    items: List[WeightedTrack] = []
    for a in agg.values():
        items.append(
            WeightedTrack(
                artist=str(a["artist"]),
                track=str(a["track"]),
                album=str(a.get("album", "")),
                ts=int(a["ts_latest"]),
                plays=int(a["plays"]),
                score=float(a["score"]),
            )
        )

    items.sort(key=lambda x: (-x.score, -x.ts, -x.plays))
    if max_unique is not None and max_unique > 0:
        items = items[:max_unique]
    return items


def unique_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
