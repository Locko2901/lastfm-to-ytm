from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ..lastfm import fetch_track_tags

if TYPE_CHECKING:
    from ..cache.tags import TagCache, TagOverrides
    from ..lastfm import Scrobble
    from ..recency import WeightedTrack

log = logging.getLogger(__name__)


def resolve_tags_for_tracks(
    tracks: Sequence[Scrobble | WeightedTrack],
    tag_cache: TagCache,
    api_key: str,
    min_count: int = 10,
    sleep_between: float = 0.25,
    max_retries: int = 3,
    tag_overrides: TagOverrides | None = None,
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Resolve Last.fm tags for a list of tracks, using cache first."""
    tag_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
    total = len(tracks)
    api_calls = 0

    for index, t in enumerate(tracks, start=1):
        key = (t.artist.lower(), t.track.lower())

        if key in tag_map:
            continue

        if tag_overrides is not None:
            override_result = tag_overrides.get(t.artist, t.track)
            if override_result is not None:
                override_tags, mode = override_result
                if mode == "replace":
                    tag_map[key] = override_tags
                    continue

        cached = tag_cache.get(t.artist, t.track)
        if cached is not None:
            tags = cached
        else:
            tags = fetch_track_tags(
                api_key,
                t.artist,
                t.track,
                min_count=min_count,
                max_retries=max_retries,
            )
            tag_cache.set(t.artist, t.track, tags)
            api_calls += 1

            if api_calls % 50 == 0:
                log.info("Tag progress: %d/%d tracks, %d API calls", index, total, api_calls)

            if sleep_between > 0:
                time.sleep(sleep_between)

        if tag_overrides is not None:
            tags = tag_overrides.apply(t.artist, t.track, tags)

        tag_map[key] = tags

    log.info("Resolved tags for %d unique tracks (%d API calls, %d cached)", len(tag_map), api_calls, len(tag_map) - api_calls)
    return tag_map
