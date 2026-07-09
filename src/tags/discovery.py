"""Discovery playlist candidate generation.

Unlike tag/artist playlists - which *filter* the user's existing scrobbles -
discovery playlists surface songs the user has **never** scrobbled. Seeds are
taken from the user's most-played tracks or artists, expanded via Last.fm's
``getSimilar`` endpoints, then filtered to exclude anything already in their
history. The resulting candidate list flows through the same
resolve-to-video-id and sync machinery as every other custom playlist.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from typing import TYPE_CHECKING

from ..lastfm import (
    Scrobble,
    fetch_artist_top_tracks,
    fetch_similar_artists,
    fetch_similar_tracks,
)

if TYPE_CHECKING:
    from ..config import CustomPlaylistConfig, Settings

log = logging.getLogger(__name__)

_MAX_SEEDS = 15
_SIMILAR_TRACKS_PER_SEED = 40
_SIMILAR_ARTISTS_PER_SEED = 6
_TOP_TRACKS_PER_ARTIST = 6
_CANDIDATE_MULTIPLIER = 3
_DEFAULT_POOL = 150


def _top_tracks(recents: list[Scrobble], count: int) -> list[tuple[str, str]]:
    """Return the ``count`` most-played (artist, track) pairs, most-played first."""
    counter: Counter[tuple[str, str]] = Counter()
    display: dict[tuple[str, str], tuple[str, str]] = {}
    for s in recents:
        key = (s.artist.lower(), s.track.lower())
        counter[key] += 1
        display.setdefault(key, (s.artist, s.track))
    return [display[key] for key, _ in counter.most_common(count)]


def _top_artists(recents: list[Scrobble], count: int) -> list[str]:
    """Return the ``count`` most-played artist names, most-played first."""
    counter: Counter[str] = Counter()
    display: dict[str, str] = {}
    for s in recents:
        key = s.artist.lower()
        counter[key] += 1
        display.setdefault(key, s.artist)
    return [display[key] for key, _ in counter.most_common(count)]


def generate_discovery_candidates(
    config: CustomPlaylistConfig,
    recents: list[Scrobble],
    settings: Settings,
) -> list[Scrobble]:
    """Build a ranked pool of never-scrobbled candidate tracks for a discovery playlist.

    Seeds come from the user's most-played tracks (``discovery_seed == "tracks"``)
    or artists (``discovery_seed == "artists"``), either chosen automatically from
    ``recents`` or supplied manually via the playlist config. Unless the playlist
    disables it via ``config.discovery_exclude_scrobbled``, candidates already
    present in ``recents`` (i.e. already scrobbled) are excluded; anything on the
    playlist's blacklist is always excluded. When ``settings.discovery_rediscover_days``
    is set, tracks whose most recent play is older than that window are *not*
    excluded, so long-forgotten favourites can resurface. The returned list is
    ordered by aggregated similarity score. Returns an empty list (with an
    explanatory warning) when Last.fm has no similar tracks/artists for the
    seeds - e.g. when the seeds are too obscure to yield recommendations.
    """
    seed_mode = config.discovery_seed if config.discovery_seed in ("artists", "tracks") else "artists"
    api_key = settings.lastfm_api_key
    max_retries = settings.lastfm_max_retries
    sleep_between = settings.tag_sleep_between

    now = int(time.time())
    if config.discovery_exclude_scrobbled:
        rediscover_days = settings.discovery_rediscover_days
        rediscover_cutoff = (now - rediscover_days * 86400) if rediscover_days > 0 else None
        scrobbled = {(s.artist.lower(), s.track.lower()) for s in recents if rediscover_cutoff is None or s.ts >= rediscover_cutoff}
    else:
        scrobbled = set()
    blacklist = config.blacklist
    blacklist_artists = config.blacklist_artists

    target_pool = (config.limit * _CANDIDATE_MULTIPLIER) if config.limit > 0 else _DEFAULT_POOL
    stop_at = target_pool * 2

    scores: dict[tuple[str, str], float] = {}
    display: dict[tuple[str, str], tuple[str, str]] = {}
    similar_returned = 0

    def add_candidate(artist: str, track: str, score: float) -> None:
        artist = artist.strip()
        track = track.strip()
        if not artist or not track:
            return
        key = (artist.lower(), track.lower())
        if key in scrobbled:
            return
        if key[0] in blacklist_artists:
            return
        if f"{key[0]}|{key[1]}" in blacklist:
            return
        display.setdefault(key, (artist, track))
        scores[key] = scores.get(key, 0.0) + max(score, 0.01)

    def _sleep() -> None:
        if sleep_between > 0:
            time.sleep(sleep_between)

    if seed_mode == "tracks":
        if config.discovery_seed_auto:
            track_seeds: list[tuple[str, str]] = _top_tracks(recents, _MAX_SEEDS)
        else:
            track_seeds = list(config.discovery_seed_tracks)
            if not track_seeds:
                log.warning("Discovery '%s': manual seeds empty, falling back to top tracks", config.name)
                track_seeds = _top_tracks(recents, _MAX_SEEDS)
        log.info("Discovery '%s': expanding %d seed track(s) via track.getSimilar", config.name, len(track_seeds))
        for artist, track in track_seeds:
            similar_tracks = fetch_similar_tracks(api_key, artist, track, _SIMILAR_TRACKS_PER_SEED, max_retries)
            similar_returned += len(similar_tracks)
            for sim in similar_tracks:
                add_candidate(sim["artist"], sim["track"], sim.get("match", 0.0))
            _sleep()
            if len(display) >= stop_at:
                break
    else:
        if config.discovery_seed_auto:
            artist_seeds: list[str] = _top_artists(recents, _MAX_SEEDS)
        else:
            artist_seeds = list(config.discovery_seed_artists)
            if not artist_seeds:
                log.warning("Discovery '%s': manual seeds empty, falling back to top artists", config.name)
                artist_seeds = _top_artists(recents, _MAX_SEEDS)
        seed_lower = {a.lower() for a in artist_seeds}
        log.info("Discovery '%s': expanding %d seed artist(s) via artist.getSimilar", config.name, len(artist_seeds))
        for artist in artist_seeds:
            similar = fetch_similar_artists(api_key, artist, _SIMILAR_ARTISTS_PER_SEED, max_retries)
            similar_returned += len(similar)
            _sleep()
            for sa in similar:
                if sa["artist"].lower() in seed_lower:
                    continue
                for top in fetch_artist_top_tracks(api_key, sa["artist"], _TOP_TRACKS_PER_ARTIST, max_retries):
                    add_candidate(top["artist"], top["track"], sa.get("match", 0.0))
                _sleep()
            if len(display) >= stop_at:
                break

    if not scores:
        seed_noun = "tracks" if seed_mode == "tracks" else "artists"
        if similar_returned == 0:
            log.warning(
                "Discovery '%s': Last.fm returned no similar %s for the seeds - they may be too "
                "obscure to find recommendations. Try broader or more mainstream seeds.",
                config.name,
                seed_noun,
            )
        else:
            log.warning(
                "Discovery '%s': all %d similar result(s) were filtered out (already scrobbled or blacklisted).",
                config.name,
                similar_returned,
            )
        return []

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    candidates = [Scrobble(artist=display[key][0], track=display[key][1], album="", ts=now) for key, _ in ranked[:target_pool]]

    log.info("Discovery '%s': %d candidate track(s) after filtering", config.name, len(candidates))
    return candidates
