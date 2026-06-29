from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..lastfm import Scrobble
    from ..recency import WeightedTrack

log = logging.getLogger(__name__)


def filter_tracks_by_tags(
    tracks: Sequence[Scrobble | WeightedTrack],
    tag_map: dict[tuple[str, str], list[dict[str, Any]]],
    wanted_tags: set[str],
    match: str = "any",
    min_count: int = 10,
    blacklist: frozenset[str] = frozenset(),
    blacklist_artists: frozenset[str] = frozenset(),
) -> list[Scrobble | WeightedTrack]:
    """Filter tracks by Last.fm tag criteria."""
    result: list[Scrobble | WeightedTrack] = []

    for t in tracks:
        key = (t.artist.lower(), t.track.lower())

        if key[0] in blacklist_artists:
            log.debug("Per-playlist artist blacklisted: %s - %s", t.artist, t.track)
            continue

        blacklist_key = f"{key[0]}|{key[1]}"
        if blacklist_key in blacklist:
            log.debug("Per-playlist blacklisted: %s - %s", t.artist, t.track)
            continue

        tags = tag_map.get(key)
        if not tags:
            continue

        track_tag_names = {tag["name"].lower() for tag in tags if tag.get("count", 0) >= min_count}

        if match == "all":
            if wanted_tags <= track_tag_names:
                result.append(t)
        elif wanted_tags & track_tag_names:
            result.append(t)

    return result
