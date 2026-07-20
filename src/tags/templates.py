"""Template ("filter") playlist candidate generation.

Filter playlists are the reusable-primitive counterpart to tag/artist/discovery
playlists. Instead of hard-coding a playlist type per idea (top tracks,
forgotten favourites, seasonal, ...), every idea is expressed as a combination
of composable filters over the user's listening history. Named *presets* simply
pre-fill a :class:`~src.config.PlaylistFilterSpec`; the same engine evaluates all
of them, so new playlist ideas usually mean a new preset rather than new code.

Time-based filters (first/last played, lifetime plays) need the user's full
scrobble history, so they work best with the local Last.fm database enabled.
When it is disabled the engine falls back to the fetched ``recents`` window and
degrades gracefully -- a note is logged and long look-back filters may match
little.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from ..config import PlaylistFilterSpec
from ..lastfm import Scrobble

if TYPE_CHECKING:
    from ..config import CustomPlaylistConfig, Settings

log = logging.getLogger(__name__)

_SECONDS_PER_DAY = 86400

_FORGOTTEN_PLAYS_PERCENTILE = 0.75
_FORGOTTEN_MIN_PLAYS_FLOOR = 2
_FORGOTTEN_STALE_PERCENTILE = 0.6
_FORGOTTEN_STALE_FLOOR_DAYS = 14

_REDISCOVERED_FIRST_PERCENTILE = 0.5
_REDISCOVERED_FIRST_FLOOR_DAYS = 180
_REDISCOVERED_RECENT_PERCENTILE = 0.3
_REDISCOVERED_RECENT_FLOOR_DAYS = 30

# Meteorological seasons (Northern hemisphere) keyed by their three months.
_SEASON_MONTHS: tuple[tuple[int, ...], ...] = (
    (12, 1, 2),  # winter
    (3, 4, 5),  # spring
    (6, 7, 8),  # summer
    (9, 10, 11),  # autumn
)

PRESETS: dict[str, PlaylistFilterSpec] = {
    "top_tracks_7d": PlaylistFilterSpec(played_within_days=7, sort="plays"),
    "top_tracks_30d": PlaylistFilterSpec(played_within_days=30, sort="plays"),
    "top_tracks_90d": PlaylistFilterSpec(played_within_days=90, sort="plays"),
    "forgotten_favorites": PlaylistFilterSpec(min_plays=_FORGOTTEN_MIN_PLAYS_FLOOR, not_played_within_days=_FORGOTTEN_STALE_FLOOR_DAYS, sort="plays"),
    "not_played_6mo": PlaylistFilterSpec(not_played_within_days=182, sort="stale"),
    "active_artists": PlaylistFilterSpec(played_within_days=30, per_artist_limit=1, sort="recent"),
    "rediscovered_artists": PlaylistFilterSpec(
        first_played_before_days=_REDISCOVERED_FIRST_FLOOR_DAYS,
        played_within_days=_REDISCOVERED_RECENT_FLOOR_DAYS,
        per_artist_limit=1,
        sort="recent",
    ),
    "new_to_me": PlaylistFilterSpec(first_played_within_days=30, sort="first_seen"),
    # "seasonal" resolves its month window at sync time (see resolve_spec).
    "seasonal": PlaylistFilterSpec(sort="plays"),
}


@dataclass(slots=True)
class _HistoryRecord:
    """A single unique track with lifetime play stats used for filtering."""

    artist: str
    track: str
    album: str
    plays: int
    first_uts: int
    last_uts: int


def _current_season_months(now: float) -> tuple[int, ...]:
    """Return the three months of the season containing ``now`` (UTC)."""
    month = datetime.fromtimestamp(now, tz=UTC).month
    for months in _SEASON_MONTHS:
        if month in months:
            return months
    return ()


def resolve_spec(config: CustomPlaylistConfig, now: float) -> PlaylistFilterSpec:
    """Return the effective filter spec for a config.

    Named presets expand to their canonical spec; ``"custom"`` uses the stored
    ``filters``. The seasonal preset resolves its month window against ``now``.
    """
    template = config.filter_template
    if template == "seasonal":
        return PlaylistFilterSpec(sort="plays", months=_current_season_months(now))
    if template in PRESETS:
        return PRESETS[template]
    return config.filters


def _pool_from_local_db(settings: Settings) -> list[_HistoryRecord]:
    """Build the candidate pool from the full local Last.fm history DB."""
    from ..lastfm import LocalScrobbleDB

    db = LocalScrobbleDB(settings.lastfm_local_db_file)
    try:
        rows = db.get_scoring_rows(min_plays=1)
    finally:
        db.close()
    return [_HistoryRecord(artist, track, album, plays, first, last) for artist, track, album, plays, first, last in rows]


def _pool_from_recents(recents: list[Scrobble]) -> list[_HistoryRecord]:
    """Aggregate raw scrobbles into unique-track records with play stats."""
    agg: dict[tuple[str, str], _HistoryRecord] = {}
    for s in recents:
        key = (s.artist.lower(), s.track.lower())
        rec = agg.get(key)
        if rec is None:
            agg[key] = _HistoryRecord(s.artist, s.track, s.album, 1, s.ts, s.ts)
            continue
        rec.plays += 1
        if s.album and not rec.album:
            rec.album = s.album
        if s.ts and (rec.first_uts == 0 or s.ts < rec.first_uts):
            rec.first_uts = s.ts
        rec.last_uts = max(rec.last_uts, s.ts)
    return list(agg.values())


def _build_pool(config: CustomPlaylistConfig, recents: list[Scrobble], settings: Settings) -> list[_HistoryRecord]:
    """Assemble the candidate pool, preferring full history when available."""
    if settings.use_local_lastfm_db:
        records = _pool_from_local_db(settings)
        if records:
            return records
        log.warning(
            "Filter playlist '%s': local Last.fm DB is empty; falling back to the recent-tracks window",
            config.name,
        )
    else:
        log.info(
            "Filter playlist '%s': local Last.fm DB disabled - time-based filters are limited to the fetched recents window",
            config.name,
        )
    return _pool_from_recents(recents)


def _blacklisted(rec: _HistoryRecord, blacklist: frozenset[str], blacklist_artists: frozenset[str]) -> bool:
    """Return True if the record is excluded by a per-playlist blacklist."""
    artist = rec.artist.lower()
    if artist in blacklist_artists:
        return True
    return f"{artist}|{rec.track.lower()}" in blacklist


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolated percentile of ``values`` (``pct`` in 0..1)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct * (len(ordered) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def _resolve_forgotten_favorites_spec(pool: list[_HistoryRecord], now: float) -> PlaylistFilterSpec:
    """Derive a dynamic forgotten-favourites spec from the pool's own stats.

    Both thresholds are percentiles of *this* library, so the same preset means
    "played 4 times, gone a month" for a small collection and "played 280 times,
    gone a couple of years" for a huge one. The floors only guard degenerate
    edges (single-listen tracks, or a library so new nothing is really old yet);
    they do not set the bar for a normal collection.
    """
    plays = [float(r.plays) for r in pool if r.plays > 0]
    ages_days = [(now - r.last_uts) / _SECONDS_PER_DAY for r in pool if r.last_uts > 0]
    min_plays = max(_FORGOTTEN_MIN_PLAYS_FLOOR, int(_percentile(plays, _FORGOTTEN_PLAYS_PERCENTILE)))
    stale_days = max(_FORGOTTEN_STALE_FLOOR_DAYS, int(_percentile(ages_days, _FORGOTTEN_STALE_PERCENTILE)))
    return PlaylistFilterSpec(min_plays=min_plays, not_played_within_days=stale_days, sort="plays")


def _resolve_rediscovered_artists_spec(pool: list[_HistoryRecord], now: float) -> PlaylistFilterSpec:
    """Derive a dynamic rediscovered-artists spec from the pool's own stats.

    Like forgotten_favorites, both windows are percentiles of *this* library:
    "long-known" means first heard longer ago than most of your collection, and
    "recently returned" means played within your fresh listening cohort. So the
    same preset means "first heard a year ago, back this month" for one library
    and "first heard five years ago, back this quarter" for another. Floors only
    guard degenerate edges (brand-new tracks, or a hyper-active library where the
    recent cohort would otherwise be just a day or two wide).
    """
    first_ages = [(now - r.first_uts) / _SECONDS_PER_DAY for r in pool if r.first_uts > 0]
    last_ages = [(now - r.last_uts) / _SECONDS_PER_DAY for r in pool if r.last_uts > 0]
    first_before = max(_REDISCOVERED_FIRST_FLOOR_DAYS, int(_percentile(first_ages, _REDISCOVERED_FIRST_PERCENTILE)))
    played_within = max(_REDISCOVERED_RECENT_FLOOR_DAYS, int(_percentile(last_ages, _REDISCOVERED_RECENT_PERCENTILE)))
    return PlaylistFilterSpec(first_played_before_days=first_before, played_within_days=played_within, per_artist_limit=1, sort="recent")


def _passes(rec: _HistoryRecord, spec: PlaylistFilterSpec, now: float) -> bool:
    """Return True if a record satisfies every active filter in ``spec``."""
    if spec.min_plays and rec.plays < spec.min_plays:
        return False
    if spec.max_plays and rec.plays > spec.max_plays:
        return False
    if spec.played_within_days:
        cutoff = now - spec.played_within_days * _SECONDS_PER_DAY
        if rec.last_uts < cutoff:
            return False
    if spec.not_played_within_days:
        cutoff = now - spec.not_played_within_days * _SECONDS_PER_DAY
        if rec.last_uts == 0 or rec.last_uts > cutoff:
            return False
    if spec.first_played_within_days:
        cutoff = now - spec.first_played_within_days * _SECONDS_PER_DAY
        if rec.first_uts == 0 or rec.first_uts < cutoff:
            return False
    if spec.first_played_before_days:
        cutoff = now - spec.first_played_before_days * _SECONDS_PER_DAY
        if rec.first_uts == 0 or rec.first_uts > cutoff:
            return False
    if spec.months:
        if rec.last_uts == 0:
            return False
        if datetime.fromtimestamp(rec.last_uts, tz=UTC).month not in spec.months:
            return False
    return True


def _rank(records: list[_HistoryRecord], sort: str) -> list[_HistoryRecord]:
    """Order records according to the spec's sort key."""
    if sort == "recent":
        return sorted(records, key=lambda r: r.last_uts, reverse=True)
    if sort == "stale":
        return sorted(records, key=lambda r: (r.last_uts, -r.plays))
    if sort == "first_seen":
        return sorted(records, key=lambda r: r.first_uts, reverse=True)
    if sort == "random":
        shuffled = list(records)
        random.shuffle(shuffled)
        return shuffled
    return sorted(records, key=lambda r: (r.plays, r.last_uts), reverse=True)


def _apply_per_artist_limit(records: list[_HistoryRecord], per_artist_limit: int) -> list[_HistoryRecord]:
    """Cap the number of tracks kept per artist, preserving rank order."""
    if per_artist_limit <= 0:
        return records
    counts: dict[str, int] = {}
    out: list[_HistoryRecord] = []
    for r in records:
        artist = r.artist.lower()
        if counts.get(artist, 0) >= per_artist_limit:
            continue
        counts[artist] = counts.get(artist, 0) + 1
        out.append(r)
    return out


def generate_template_candidates(
    config: CustomPlaylistConfig,
    recents: list[Scrobble],
    settings: Settings,
) -> list[Scrobble]:
    """Generate ranked candidate tracks for a template ("filter") playlist.

    The pool is drawn from the full local Last.fm history when enabled, otherwise
    aggregated from the fetched ``recents``. Composable filters are applied, the
    survivors ranked and optionally capped per artist. The caller trims the
    result to the playlist's ``limit`` and resolves each track to a video ID.
    """
    now = time.time()
    spec = resolve_spec(config, now)
    pool = _build_pool(config, recents, settings)

    if config.filter_template == "forgotten_favorites":
        spec = _resolve_forgotten_favorites_spec(pool, now)
    elif config.filter_template == "rediscovered_artists":
        spec = _resolve_rediscovered_artists_spec(pool, now)

    filtered = [r for r in pool if not _blacklisted(r, config.blacklist, config.blacklist_artists) and _passes(r, spec, now)]
    ranked = _rank(filtered, spec.sort)
    limited = _apply_per_artist_limit(ranked, spec.per_artist_limit)

    log.info(
        "Filter playlist '%s' (template=%s, sort=%s): %d/%d unique tracks matched",
        config.name,
        config.filter_template,
        spec.sort,
        len(limited),
        len(pool),
    )
    return [Scrobble(artist=r.artist, track=r.track, album=r.album, ts=r.last_uts) for r in limited]
