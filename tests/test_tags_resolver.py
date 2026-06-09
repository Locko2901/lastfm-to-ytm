"""Tests for ``resolve_tags_for_tracks`` (cache-first + override modes)."""

from __future__ import annotations

import src.tags.resolver as resolver_mod
from src.cache.tags import TagCache, TagOverrides
from src.lastfm import Scrobble
from src.tags.resolver import resolve_tags_for_tracks


def _scrobble(artist: str, track: str) -> Scrobble:
    return Scrobble(artist=artist, track=track, album="Album", ts=0)


def _tag_cache(tmp_path) -> TagCache:
    return TagCache(str(tmp_path / ".tag_cache.json"))


def _tag_overrides(tmp_path) -> TagOverrides:
    return TagOverrides(str(tmp_path / "tag_overrides.json"))


def _resolve(tracks, cache, **kwargs):
    return resolve_tags_for_tracks(
        tracks=tracks,
        tag_cache=cache,
        api_key="key",
        sleep_between=0.0,
        **kwargs,
    )


def test_cache_hit_skips_api(tmp_path, monkeypatch):
    cache = _tag_cache(tmp_path)
    cache.set("Artist", "Title", [{"name": "rock", "count": 100}])

    def _fail(*_a, **_k):
        raise AssertionError("fetch_track_tags should not run on a cache hit")

    monkeypatch.setattr(resolver_mod, "fetch_track_tags", _fail)

    result = _resolve([_scrobble("Artist", "Title")], cache)

    assert result[("artist", "title")] == [{"name": "rock", "count": 100}]


def test_api_fetch_populates_cache(tmp_path, monkeypatch):
    cache = _tag_cache(tmp_path)
    calls: list[tuple] = []

    def _fetch(_key, artist, title, **_k):
        calls.append((artist, title))
        return [{"name": "pop", "count": 80}]

    monkeypatch.setattr(resolver_mod, "fetch_track_tags", _fetch)

    result = _resolve([_scrobble("Artist", "Title")], cache)

    assert result[("artist", "title")] == [{"name": "pop", "count": 80}]
    assert len(calls) == 1
    assert cache.get("Artist", "Title") == [{"name": "pop", "count": 80}]


def test_duplicate_tracks_fetched_once(tmp_path, monkeypatch):
    cache = _tag_cache(tmp_path)
    calls: list[tuple] = []

    def _fetch(_key, artist, title, **_k):
        calls.append((artist, title))
        return [{"name": "jazz", "count": 50}]

    monkeypatch.setattr(resolver_mod, "fetch_track_tags", _fetch)

    _resolve([_scrobble("Artist", "Title"), _scrobble("artist", "title")], cache)

    assert len(calls) == 1


def test_override_replace_mode_skips_api(tmp_path, monkeypatch):
    cache = _tag_cache(tmp_path)
    overrides = _tag_overrides(tmp_path)
    overrides.set("Artist", "Title", ["metal"], mode="replace")

    def _fail(*_a, **_k):
        raise AssertionError("fetch_track_tags should not run in replace mode")

    monkeypatch.setattr(resolver_mod, "fetch_track_tags", _fail)

    result = _resolve([_scrobble("Artist", "Title")], cache, tag_overrides=overrides)

    names = [t["name"] for t in result[("artist", "title")]]
    assert names == ["metal"]


def test_override_add_mode_merges_with_api(tmp_path, monkeypatch):
    cache = _tag_cache(tmp_path)
    overrides = _tag_overrides(tmp_path)
    overrides.set("Artist", "Title", ["custom"], mode="add")

    monkeypatch.setattr(
        resolver_mod,
        "fetch_track_tags",
        lambda *_a, **_k: [{"name": "rock", "count": 90}],
    )

    result = _resolve([_scrobble("Artist", "Title")], cache, tag_overrides=overrides)

    names = [t["name"] for t in result[("artist", "title")]]
    assert "custom" in names
    assert "rock" in names
