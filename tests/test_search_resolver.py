"""Tests for the three-tier search priority resolver.

``resolve_tracks_to_video_ids`` is the heart of track resolution:
1. manual overrides, 2. cache (incl. negative caching), 3. YTM API.
We stub ``find_on_ytm`` so these tests stay pure and offline.
"""

from __future__ import annotations

import src.search.resolver as resolver_mod
from src.cache.search import SearchCache, SearchOverrides
from src.lastfm import Scrobble
from src.recency import WeightedTrack
from src.search.resolver import resolve_tracks_to_video_ids


def _scrobble(artist: str, track: str, album: str = "Album") -> Scrobble:
    return Scrobble(artist=artist, track=track, album=album, ts=0)


def _make_caches(tmp_path):
    cache = SearchCache(str(tmp_path / ".search_cache.json"))
    overrides = SearchOverrides(str(tmp_path / "search_overrides.json"))
    return cache, overrides


def _resolve(tmp_path, tracks, *, cache=None, overrides=None, **kwargs):
    if cache is None or overrides is None:
        c, o = _make_caches(tmp_path)
        cache = cache or c
        overrides = overrides or o
    return resolve_tracks_to_video_ids(
        ytm_search=object(),
        tracks=tracks,
        sleep_between=0.0,
        early_termination_score=0.9,
        search_cache=cache,
        search_overrides=overrides,
        **kwargs,
    )


def test_override_takes_priority(tmp_path, monkeypatch):
    cache, overrides = _make_caches(tmp_path)
    overrides.set("Artist", "Title", "override_vid")

    def _fail(*_a, **_k):
        raise AssertionError("find_on_ytm should not run when an override exists")

    monkeypatch.setattr(resolver_mod, "find_on_ytm", _fail)

    vids, misses, mapping, run_log = _resolve(tmp_path, [_scrobble("Artist", "Title")], cache=cache, overrides=overrides)

    assert vids == ["override_vid"]
    assert misses == 0
    assert mapping[("artist", "title")] == "override_vid"
    assert run_log[0]["source"] == "override"


def test_cache_hit_skips_api(tmp_path, monkeypatch):
    cache, overrides = _make_caches(tmp_path)
    cache.set("Artist", "Title", "cached_vid", yt_title="Artist - Title")

    def _fail(*_a, **_k):
        raise AssertionError("find_on_ytm should not run on a cache hit")

    monkeypatch.setattr(resolver_mod, "find_on_ytm", _fail)

    vids, misses, _mapping, run_log = _resolve(tmp_path, [_scrobble("Artist", "Title")], cache=cache, overrides=overrides)

    assert vids == ["cached_vid"]
    assert misses == 0
    assert run_log[0]["source"] == "cache"


def test_api_fallback_populates_cache(tmp_path, monkeypatch):
    cache, overrides = _make_caches(tmp_path)
    calls: list[tuple] = []

    def _found(_ytm, artist, title, *_a, **_k):
        calls.append((artist, title))
        return ("api_vid", "Artist - Title (Official)")

    monkeypatch.setattr(resolver_mod, "find_on_ytm", _found)

    vids, misses, _mapping, run_log = _resolve(tmp_path, [_scrobble("Artist", "Title")], cache=cache, overrides=overrides)

    assert vids == ["api_vid"]
    assert misses == 0
    assert run_log[0]["source"] == "search"
    assert len(calls) == 1
    assert cache.get("Artist", "Title") == "api_vid"


def test_api_miss_is_negatively_cached(tmp_path, monkeypatch):
    cache, overrides = _make_caches(tmp_path)
    call_count = {"n": 0}

    def _not_found(*_a, **_k):
        call_count["n"] += 1

    monkeypatch.setattr(resolver_mod, "find_on_ytm", _not_found)

    vids, misses, _mapping, run_log = _resolve(tmp_path, [_scrobble("Artist", "Title")], cache=cache, overrides=overrides)

    assert vids == []
    assert misses == 1
    assert run_log[0]["source"] == "not_found"
    _resolve(tmp_path, [_scrobble("Artist", "Title")], cache=cache, overrides=overrides)
    assert call_count["n"] == 1


def test_cached_not_found_reports_source(tmp_path, monkeypatch):
    cache, overrides = _make_caches(tmp_path)
    cache.set("Artist", "Title", None)

    def _fail(*_a, **_k):
        raise AssertionError("find_on_ytm should not run on a cached miss")

    monkeypatch.setattr(resolver_mod, "find_on_ytm", _fail)

    vids, misses, _mapping, run_log = _resolve(tmp_path, [_scrobble("Artist", "Title")], cache=cache, overrides=overrides)

    assert vids == []
    assert misses == 1
    assert run_log[0]["source"] == "not_found_cached"


def test_blacklisted_track_skipped(tmp_path, monkeypatch):
    cache, overrides = _make_caches(tmp_path)
    overrides._cache["_blacklist"][overrides._make_key("Artist", "Title")] = {
        "reason": "live version only",
    }

    def _fail(*_a, **_k):
        raise AssertionError("find_on_ytm should not run for a blacklisted track")

    monkeypatch.setattr(resolver_mod, "find_on_ytm", _fail)

    vids, misses, _mapping, run_log = _resolve(tmp_path, [_scrobble("Artist", "Title")], cache=cache, overrides=overrides)

    assert vids == []
    assert misses == 1
    assert run_log[0]["source"] == "blacklisted"


def test_duplicate_video_ids_collapsed(tmp_path, monkeypatch):
    cache, overrides = _make_caches(tmp_path)
    cache.set("Artist A", "Song", "shared_vid")
    cache.set("Artist B", "Cover", "shared_vid")

    monkeypatch.setattr(resolver_mod, "find_on_ytm", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError()))

    vids, misses, mapping, _run_log = _resolve(
        tmp_path,
        [_scrobble("Artist A", "Song"), _scrobble("Artist B", "Cover")],
        cache=cache,
        overrides=overrides,
    )

    assert vids == ["shared_vid"]
    assert misses == 0
    assert mapping == {("artist a", "song"): "shared_vid"}


def test_weighted_track_resolves(tmp_path, monkeypatch):
    cache, overrides = _make_caches(tmp_path)
    cache.set("Artist", "Title", "wvid")
    monkeypatch.setattr(resolver_mod, "find_on_ytm", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError()))

    wt = WeightedTrack(artist="Artist", track="Title", album="Album", ts=0, plays=5, score=0.8)
    vids, misses, _mapping, _run_log = _resolve(tmp_path, [wt], cache=cache, overrides=overrides)

    assert vids == ["wvid"]
    assert misses == 0
