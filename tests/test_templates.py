"""Tests for the template ("filter") playlist engine (src/tags/templates.py)."""

from __future__ import annotations

import time
from dataclasses import dataclass

from src.config import CustomPlaylistConfig, PlaylistFilterSpec
from src.lastfm import LocalScrobbleDB, Scrobble
from src.tags import templates

_DAY = 86400
_NOW = int(time.time())


@dataclass
class _StubSettings:
    use_local_lastfm_db: bool = False
    lastfm_local_db_file: str = ""


def _scrobble(artist: str, track: str, *, days_ago: float = 0.0) -> Scrobble:
    return Scrobble(artist=artist, track=track, album="", ts=int(_NOW - days_ago * _DAY))


def _filter_config(name: str = "F", template: str = "custom", **filters) -> CustomPlaylistConfig:
    spec = PlaylistFilterSpec(**filters) if filters else PlaylistFilterSpec()
    return CustomPlaylistConfig(name=name, kind="filter", filter_template=template, filters=spec, limit=0)


def test_resolve_spec_returns_preset():
    cfg = _filter_config(template="forgotten_favorites")
    spec = templates.resolve_spec(cfg, _NOW)
    assert spec.min_plays == templates._FORGOTTEN_MIN_PLAYS_FLOOR
    assert spec.not_played_within_days == templates._FORGOTTEN_STALE_FLOOR_DAYS
    assert spec.sort == "plays"


def test_resolve_spec_custom_uses_config_filters():
    cfg = _filter_config(template="custom", min_plays=7, sort="recent")
    spec = templates.resolve_spec(cfg, _NOW)
    assert spec.min_plays == 7
    assert spec.sort == "recent"


def test_resolve_spec_seasonal_fills_current_months():
    cfg = _filter_config(template="seasonal")
    spec = templates.resolve_spec(cfg, _NOW)
    assert len(spec.months) == 3
    from datetime import UTC, datetime

    assert datetime.fromtimestamp(_NOW, tz=UTC).month in spec.months


def test_top_tracks_preset_filters_window_and_ranks_by_plays():
    recents = [
        # Old track (played 200 days ago) should be excluded by the 30-day window.
        _scrobble("Old", "Song", days_ago=200),
        # Recent, most-played -> ranked first.
        *[_scrobble("Fresh", "Hit", days_ago=1) for _ in range(3)],
        _scrobble("Fresh", "Filler", days_ago=2),
    ]
    cfg = _filter_config(template="top_tracks_30d")
    out = templates.generate_template_candidates(cfg, recents, _StubSettings())
    keys = [(c.artist, c.track) for c in out]
    assert ("Old", "Song") not in keys
    assert keys[0] == ("Fresh", "Hit")
    assert ("Fresh", "Filler") in keys


def test_forgotten_favorites_surfaces_small_library_relative():
    recents = [
        *[_scrobble("Fav", "Gem", days_ago=30) for _ in range(4)],
        *[_scrobble(f"Now{i}", "T", days_ago=i + 1) for i in range(5)],
    ]
    cfg = _filter_config(template="forgotten_favorites")
    out = templates.generate_template_candidates(cfg, recents, _StubSettings())
    keys = [(c.artist, c.track) for c in out]
    assert ("Fav", "Gem") in keys
    assert all(a.startswith("Now") is False for a, _ in keys)


def test_forgotten_favorites_excludes_recent_and_rare():
    recents = [
        # Current rotation: single-play tracks heard in the last ~10 days.
        *[_scrobble(f"Now{i}", "T", days_ago=i + 1) for i in range(10)],
        # A favourite still in rotation (recent) -> excluded (not forgotten).
        *[_scrobble("FavRecent", "Hot", days_ago=5) for _ in range(6)],
        # A favourite gone quiet for months -> included.
        *[_scrobble("FavOld", "Gem", days_ago=120) for _ in range(6)],
        # Old but only heard once -> excluded (never a favourite).
        _scrobble("OldRare", "Blip", days_ago=300),
    ]
    cfg = _filter_config(template="forgotten_favorites")
    out = templates.generate_template_candidates(cfg, recents, _StubSettings())
    keys = [(c.artist, c.track) for c in out]
    assert ("FavOld", "Gem") in keys
    assert ("FavRecent", "Hot") not in keys
    assert ("OldRare", "Blip") not in keys


def test_forgotten_favorites_lookback_scales_with_library():
    recents = []
    for i in range(30):
        recents += [_scrobble(f"Old{i}", "Song", days_ago=730 + i * 30) for _ in range(20)]
    recents += [_scrobble("YearAgo", "Fav", days_ago=365) for _ in range(20)]
    cfg = _filter_config(template="forgotten_favorites")
    spec = templates._resolve_forgotten_favorites_spec(templates._pool_from_recents(recents), _NOW)
    assert spec.not_played_within_days > templates._FORGOTTEN_STALE_FLOOR_DAYS
    out = templates.generate_template_candidates(cfg, recents, _StubSettings())
    keys = [(c.artist, c.track) for c in out]
    assert ("YearAgo", "Fav") not in keys  # too recent relative to the dormant tail
    assert any(a.startswith("Old") for a, _ in keys)  # genuinely dormant favourites remain


def test_new_to_me_uses_first_played_window_and_first_seen_sort():
    recents = [
        # First heard 10 days ago -> new to me, and first_seen sort puts newest first.
        _scrobble("NewOne", "A", days_ago=10),
        # First heard 5 days ago -> newer discovery.
        _scrobble("NewTwo", "B", days_ago=5),
        # First heard 400 days ago -> not new.
        _scrobble("OldOne", "C", days_ago=400),
    ]
    cfg = _filter_config(template="new_to_me")
    out = templates.generate_template_candidates(cfg, recents, _StubSettings())
    keys = [(c.artist, c.track) for c in out]
    assert ("OldOne", "C") not in keys
    assert keys[0] == ("NewTwo", "B")  # most recent first-play first


def test_active_artists_caps_one_per_artist_ordered_by_recency():
    recents = [
        _scrobble("ArtistA", "Song1", days_ago=2),
        _scrobble("ArtistA", "Song2", days_ago=10),  # same artist, older -> dropped by per-artist cap
        _scrobble("ArtistB", "Song3", days_ago=1),  # most recent artist -> first
    ]
    cfg = _filter_config(template="active_artists")
    out = templates.generate_template_candidates(cfg, recents, _StubSettings())
    keys = [(c.artist, c.track) for c in out]
    assert keys == [("ArtistB", "Song3"), ("ArtistA", "Song1")]


def test_custom_months_filter():
    from datetime import UTC, datetime

    month = datetime.fromtimestamp(_NOW, tz=UTC).month
    other = 12 if month != 12 else 6
    recents = [
        _scrobble("InMonth", "Keep", days_ago=0),
        _scrobble("Other", "Drop", days_ago=0),
    ]
    # Only keep tracks whose last play month == the wrong month; InMonth should drop.
    cfg = _filter_config(months=(other,))
    out = templates.generate_template_candidates(cfg, recents, _StubSettings())
    assert out == []  # neither track was played in `other` month (both played "now")


def test_blacklist_excludes_tracks_and_artists():
    recents = [
        _scrobble("Blocked", "X", days_ago=1),
        _scrobble("Band", "BadSong", days_ago=1),
        _scrobble("Band", "GoodSong", days_ago=1),
    ]
    cfg = CustomPlaylistConfig(
        name="F",
        kind="filter",
        filter_template="custom",
        filters=PlaylistFilterSpec(sort="plays"),
        limit=0,
        blacklist=frozenset({"band|badsong"}),
        blacklist_artists=frozenset({"blocked"}),
    )
    out = templates.generate_template_candidates(cfg, recents, _StubSettings())
    keys = [(c.artist, c.track) for c in out]
    assert keys == [("Band", "GoodSong")]


def test_pool_from_local_db_used_when_enabled(tmp_path):
    db_path = tmp_path / "hist.db"
    db = LocalScrobbleDB(db_path)
    # Two scrobbles of the same track: first 300 days ago, last 5 days ago.
    db.ingest_scrobbles([_scrobble("Loyal", "Anthem", days_ago=300)])
    db.ingest_scrobbles([_scrobble("Loyal", "Anthem", days_ago=5)])
    db.close()

    cfg = _filter_config(template="custom", min_plays=2, sort="plays")
    settings = _StubSettings(use_local_lastfm_db=True, lastfm_local_db_file=str(db_path))
    # recents intentionally empty: the DB is the source of truth.
    out = templates.generate_template_candidates(cfg, [], settings)
    keys = [(c.artist, c.track) for c in out]
    assert keys == [("Loyal", "Anthem")]


def test_local_db_first_played_before_filter(tmp_path):
    db_path = tmp_path / "hist.db"
    db = LocalScrobbleDB(db_path)
    db.ingest_scrobbles([_scrobble("Established", "Classic", days_ago=500)])
    db.ingest_scrobbles([_scrobble("Established", "Classic", days_ago=5)])
    db.ingest_scrobbles([_scrobble("Newcomer", "Debut", days_ago=10)])
    db.close()

    # rediscovered_artists: first heard long ago (dynamic) AND played recently.
    cfg = _filter_config(template="rediscovered_artists")
    settings = _StubSettings(use_local_lastfm_db=True, lastfm_local_db_file=str(db_path))
    out = templates.generate_template_candidates(cfg, [], settings)
    keys = [(c.artist, c.track) for c in out]
    assert keys == [("Established", "Classic")]


def test_rediscovered_artists_caps_one_per_artist_and_skips_newcomers():
    recents = [
        # Old artist, two tracks, both first heard long ago but replayed recently.
        _scrobble("Old", "A", days_ago=400),
        _scrobble("Old", "A", days_ago=5),
        _scrobble("Old", "B", days_ago=380),
        _scrobble("Old", "B", days_ago=3),
        # Newcomer: first heard recently -> not a rediscovery.
        _scrobble("New", "C", days_ago=20),
        _scrobble("New", "C", days_ago=2),
        # Filler tracks first heard recently, to anchor the distribution.
        *[_scrobble(f"F{i}", "T", days_ago=i + 1) for i in range(4)],
    ]
    cfg = _filter_config(template="rediscovered_artists")
    out = templates.generate_template_candidates(cfg, recents, _StubSettings())
    keys = [(c.artist, c.track) for c in out]
    assert ("New", "C") not in keys
    assert [a for a, _ in keys].count("Old") == 1  # per-artist cap
    assert ("Old", "B") in keys  # most recently revisited kept first


def test_rediscovered_artists_windows_scale_with_library():
    recents = []
    for i in range(20):
        recents += [_scrobble(f"Long{i}", "S", days_ago=1000 + i * 20), _scrobble(f"Long{i}", "S", days_ago=3)]
    spec = templates._resolve_rediscovered_artists_spec(templates._pool_from_recents(recents), _NOW)
    assert spec.first_played_before_days > templates._REDISCOVERED_FIRST_FLOOR_DAYS
    assert spec.per_artist_limit == 1
    assert spec.sort == "recent"
