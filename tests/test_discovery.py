from dataclasses import dataclass

from src.config import CustomPlaylistConfig
from src.lastfm import Scrobble
from src.tags import discovery


@dataclass
class _StubSettings:
    lastfm_api_key: str = "key"
    lastfm_max_retries: int = 1
    tag_sleep_between: float = 0.0
    discovery_rediscover_days: int = 0


def _scrobble(artist, track, ts=0):
    return Scrobble(artist=artist, track=track, album="", ts=ts)


def test_discovery_tracks_seed_excludes_scrobbled_and_ranks(monkeypatch):
    recents = [
        _scrobble("Seed Artist", "Seed Song"),
        _scrobble("Seed Artist", "Seed Song"),  # most played -> top seed
        _scrobble("Other", "Old Favorite"),
    ]

    def fake_similar_tracks(api_key, artist, track, limit, max_retries):
        # Only the most-played seed returns candidates; other seeds return nothing.
        if (artist, track) != ("Seed Artist", "Seed Song"):
            return []
        return [
            {"artist": "New Band", "track": "Fresh Track", "match": 0.9},
            {"artist": "Other", "track": "Old Favorite", "match": 0.8},  # already scrobbled -> excluded
            {"artist": "Second Band", "track": "Another New", "match": 0.4},
        ]

    monkeypatch.setattr(discovery, "fetch_similar_tracks", fake_similar_tracks)

    config = CustomPlaylistConfig(name="Discover", kind="discovery", discovery_seed="tracks", limit=10)
    candidates = discovery.generate_discovery_candidates(config, recents, _StubSettings())

    keys = [(c.artist, c.track) for c in candidates]
    assert ("Other", "Old Favorite") not in keys
    assert keys[0] == ("New Band", "Fresh Track")
    assert ("Second Band", "Another New") in keys


def test_discovery_tracks_seed_respects_blacklists(monkeypatch):
    recents = [_scrobble("Seed Artist", "Seed Song")]

    def fake_similar_tracks(api_key, artist, track, limit, max_retries):
        return [
            {"artist": "Blocked Artist", "track": "X", "match": 0.9},
            {"artist": "Band", "track": "Blocked Track", "match": 0.8},
            {"artist": "Band", "track": "Allowed", "match": 0.7},
        ]

    monkeypatch.setattr(discovery, "fetch_similar_tracks", fake_similar_tracks)

    config = CustomPlaylistConfig(
        name="Discover",
        kind="discovery",
        discovery_seed="tracks",
        limit=10,
        blacklist=frozenset({"band|blocked track"}),
        blacklist_artists=frozenset({"blocked artist"}),
    )
    candidates = discovery.generate_discovery_candidates(config, recents, _StubSettings())

    keys = [(c.artist, c.track) for c in candidates]
    assert keys == [("Band", "Allowed")]


def test_discovery_artists_seed_pulls_top_tracks_of_similar_artists(monkeypatch):
    recents = [_scrobble("Top Artist", "Song A"), _scrobble("Top Artist", "Song B")]

    def fake_similar_artists(api_key, artist, limit, max_retries):
        assert artist == "Top Artist"
        return [
            {"artist": "Similar One", "match": 0.9},
            {"artist": "Top Artist", "match": 1.0},  # user's own seed -> skipped
        ]

    def fake_artist_top_tracks(api_key, artist, limit, max_retries):
        assert artist == "Similar One"
        return [{"artist": "Similar One", "track": "Their Hit"}]

    monkeypatch.setattr(discovery, "fetch_similar_artists", fake_similar_artists)
    monkeypatch.setattr(discovery, "fetch_artist_top_tracks", fake_artist_top_tracks)

    config = CustomPlaylistConfig(name="Discover", kind="discovery", discovery_seed="artists", limit=10)
    candidates = discovery.generate_discovery_candidates(config, recents, _StubSettings())

    keys = [(c.artist, c.track) for c in candidates]
    assert keys == [("Similar One", "Their Hit")]


def test_discovery_manual_track_seeds_override_auto(monkeypatch):
    recents = [_scrobble("Auto Seed", "Auto Song"), _scrobble("Auto Seed", "Auto Song")]
    seen = []

    def fake_similar_tracks(api_key, artist, track, limit, max_retries):
        seen.append((artist, track))
        return [{"artist": "New Band", "track": "Fresh", "match": 0.9}]

    monkeypatch.setattr(discovery, "fetch_similar_tracks", fake_similar_tracks)

    config = CustomPlaylistConfig(
        name="Discover",
        kind="discovery",
        discovery_seed="tracks",
        discovery_seed_auto=False,
        discovery_seed_tracks=(("Manual Artist", "Manual Song"),),
        limit=10,
    )
    candidates = discovery.generate_discovery_candidates(config, recents, _StubSettings())

    assert seen == [("Manual Artist", "Manual Song")]
    assert [(c.artist, c.track) for c in candidates] == [("New Band", "Fresh")]


def test_discovery_manual_artist_seeds_override_auto(monkeypatch):
    recents = [_scrobble("Auto Seed", "Auto Song")]
    seen = []

    def fake_similar_artists(api_key, artist, limit, max_retries):
        seen.append(artist)
        return [{"artist": "Similar One", "match": 0.9}]

    def fake_artist_top_tracks(api_key, artist, limit, max_retries):
        return [{"artist": "Similar One", "track": "Their Hit"}]

    monkeypatch.setattr(discovery, "fetch_similar_artists", fake_similar_artists)
    monkeypatch.setattr(discovery, "fetch_artist_top_tracks", fake_artist_top_tracks)

    config = CustomPlaylistConfig(
        name="Discover",
        kind="discovery",
        discovery_seed="artists",
        discovery_seed_auto=False,
        discovery_seed_artists=("Manual Artist",),
        limit=10,
    )
    candidates = discovery.generate_discovery_candidates(config, recents, _StubSettings())

    assert seen == ["Manual Artist"]
    assert [(c.artist, c.track) for c in candidates] == [("Similar One", "Their Hit")]


def test_discovery_rediscover_window_allows_old_favorites(monkeypatch):
    now = 1_000_000_000
    recents = [
        _scrobble("Seed Artist", "Seed Song", ts=now),
        _scrobble("Recent", "Recent Play", ts=now),
        _scrobble("Old", "Old Favorite", ts=now - 60 * 86400),  # 60 days ago -> eligible
    ]

    def fake_similar_tracks(api_key, artist, track, limit, max_retries):
        return [
            {"artist": "Recent", "track": "Recent Play", "match": 0.9},
            {"artist": "Old", "track": "Old Favorite", "match": 0.8},
        ]

    monkeypatch.setattr(discovery, "fetch_similar_tracks", fake_similar_tracks)
    monkeypatch.setattr(discovery.time, "time", lambda: now)

    config = CustomPlaylistConfig(name="Discover", kind="discovery", discovery_seed="tracks", limit=10)
    settings = _StubSettings(discovery_rediscover_days=30)
    candidates = discovery.generate_discovery_candidates(config, recents, settings)

    keys = [(c.artist, c.track) for c in candidates]
    assert ("Recent", "Recent Play") not in keys
    assert ("Old", "Old Favorite") in keys


def test_discovery_exclude_scrobbled_off_keeps_heard_tracks(monkeypatch):
    recents = [
        _scrobble("Seed Artist", "Seed Song"),
        _scrobble("Heard Band", "Heard Song"),  # already scrobbled
    ]

    def fake_similar_tracks(api_key, artist, track, limit, max_retries):
        return [
            {"artist": "Heard Band", "track": "Heard Song", "match": 0.9},
            {"artist": "New Band", "track": "Fresh", "match": 0.5},
        ]

    monkeypatch.setattr(discovery, "fetch_similar_tracks", fake_similar_tracks)

    config = CustomPlaylistConfig(
        name="Discover",
        kind="discovery",
        discovery_seed="tracks",
        discovery_exclude_scrobbled=False,
        limit=10,
    )
    candidates = discovery.generate_discovery_candidates(config, recents, _StubSettings())

    keys = [(c.artist, c.track) for c in candidates]
    # With exclusion off, the already-scrobbled track stays in the pool.
    assert ("Heard Band", "Heard Song") in keys
    assert ("New Band", "Fresh") in keys


def test_discovery_empty_lastfm_response_returns_empty_with_warning(monkeypatch, caplog):
    recents = [_scrobble("Obscure Artist", "Obscure Song")]

    def fake_similar_tracks(api_key, artist, track, limit, max_retries):
        # Last.fm has nothing similar for these obscure seeds.
        return []

    monkeypatch.setattr(discovery, "fetch_similar_tracks", fake_similar_tracks)

    config = CustomPlaylistConfig(name="Discover", kind="discovery", discovery_seed="tracks", limit=10)
    with caplog.at_level("WARNING"):
        candidates = discovery.generate_discovery_candidates(config, recents, _StubSettings())

    assert candidates == []
    assert any("no similar tracks" in r.message.lower() for r in caplog.records)


def test_discovery_all_filtered_out_reports_distinct_warning(monkeypatch, caplog):
    recents = [_scrobble("Seed Artist", "Seed Song")]

    def fake_similar_tracks(api_key, artist, track, limit, max_retries):
        # Last.fm returns results, but every one is already scrobbled.
        return [{"artist": "Seed Artist", "track": "Seed Song", "match": 0.9}]

    monkeypatch.setattr(discovery, "fetch_similar_tracks", fake_similar_tracks)

    config = CustomPlaylistConfig(name="Discover", kind="discovery", discovery_seed="tracks", limit=10)
    with caplog.at_level("WARNING"):
        candidates = discovery.generate_discovery_candidates(config, recents, _StubSettings())

    assert candidates == []
    assert any("filtered out" in r.message.lower() for r in caplog.records)
