import pytest

from src.cache.search import SearchCache
from src.playlist.sync import (
    InvalidVideoIDsError,
    _are_same_song,
    _evict_from_cache,
    _get_playlist_video_ids,
    _reorder_playlist,
    _retry_with_backoff,
    _validate_video_ids,
)


def test_retry_returns_on_first_success():
    calls = []

    def ok():
        calls.append(1)
        return "done"

    assert _retry_with_backoff(ok, operation="x") == "done"
    assert len(calls) == 1


def test_retry_does_not_retry_terminal_status(monkeypatch):
    monkeypatch.setattr("src.playlist.sync.time.sleep", lambda _s: None)
    calls = []

    def bad():
        calls.append(1)
        raise RuntimeError("Server returned HTTP 400: Bad Request")

    with pytest.raises(RuntimeError):
        _retry_with_backoff(bad, max_retries=3, operation="x")
    assert len(calls) == 1


def test_retry_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("src.playlist.sync.time.sleep", lambda _s: None)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("Server returned HTTP 503: Service Unavailable")
        return "ok"

    assert _retry_with_backoff(flaky, max_retries=3, operation="x") == "ok"
    assert len(calls) == 3


def test_retry_exhausts_and_raises(monkeypatch):
    monkeypatch.setattr("src.playlist.sync.time.sleep", lambda _s: None)
    calls = []

    def always_429():
        calls.append(1)
        raise RuntimeError("HTTP 429: Too Many Requests")

    with pytest.raises(RuntimeError):
        _retry_with_backoff(always_429, max_retries=3, operation="x")
    assert len(calls) == 3


class FakeYTM:
    def __init__(self, playlist=None, songs=None, invalid_ids=None):
        self._playlist = playlist or {}
        self._songs = songs or {}
        self._invalid_ids = set(invalid_ids or [])
        self.moves = []

    def get_playlist(self, _playlist_id, **_kwargs):
        return self._playlist

    def get_song(self, video_id):
        if video_id in self._invalid_ids:
            raise RuntimeError("not found")
        return self._songs.get(video_id, {})

    def edit_playlist(self, _playlist_id, moveItem=None):
        self.moves.append(moveItem)
        return {"status": "STATUS_SUCCEEDED"}


def test_get_playlist_video_ids_filters_invalid_length():
    ytm = FakeYTM(
        playlist={
            "tracks": [
                {"videoId": "abcdefghijk"},
                {"videoId": "short"},
                {"videoId": None},
                {"videoId": "lmnopqrstuv"},
            ]
        }
    )
    assert _get_playlist_video_ids(ytm, "PL1") == ["abcdefghijk", "lmnopqrstuv"]


def test_validate_video_ids_reports_invalid():
    ytm = FakeYTM(songs={"good1234567": {}}, invalid_ids=["bad12345678"])
    invalid = _validate_video_ids(ytm, ["good1234567", "bad12345678"])
    assert invalid == ["bad12345678"]


def test_validate_video_ids_all_valid():
    ytm = FakeYTM(songs={"a": {}, "b": {}})
    assert _validate_video_ids(ytm, ["a", "b"]) == []


def test_evict_from_cache_removes_matching(tmp_path):
    cache = SearchCache(str(tmp_path / ".search_cache.json"))
    cache.set("Artist", "Title", "vid12345678")
    cache.set("Other", "Song", "keepme00000")
    _evict_from_cache(cache, ["vid12345678"])
    assert cache.get("Artist", "Title") is None
    assert cache.get("Other", "Song") == "keepme00000"


def test_evict_from_cache_noop_for_empty(tmp_path):
    cache = SearchCache(str(tmp_path / ".search_cache.json"))
    cache.set("Artist", "Title", "vid12345678")
    _evict_from_cache(cache, [])
    assert cache.get("Artist", "Title") == "vid12345678"


def test_evict_from_cache_handles_none_cache():
    _evict_from_cache(None, ["anything"])


def test_are_same_song_identical_ids_short_circuits():
    ytm = FakeYTM()
    assert _are_same_song(ytm, "samevid0000", "samevid0000") is True


def test_are_same_song_detects_substitution():
    ytm = FakeYTM(
        songs={
            "vid1": {"title": "One More Time", "artists": [{"name": "Daft Punk"}]},
            "vid2": {"title": "Daft Punk - One More Time (Official Audio)", "artists": [{"name": "Daft Punk"}]},
        }
    )
    assert _are_same_song(ytm, "vid1", "vid2") is True


def test_are_same_song_different_songs():
    ytm = FakeYTM(
        songs={
            "vid1": {"title": "One More Time", "artists": [{"name": "Daft Punk"}]},
            "vid2": {"title": "Bohemian Rhapsody", "artists": [{"name": "Queen"}]},
        }
    )
    assert _are_same_song(ytm, "vid1", "vid2") is False


def test_reorder_no_moves_when_already_ordered():
    ytm = FakeYTM(
        playlist={
            "tracks": [
                {"videoId": "aaaaaaaaaaa", "setVideoId": "s1"},
                {"videoId": "bbbbbbbbbbb", "setVideoId": "s2"},
            ]
        }
    )
    moves = _reorder_playlist(ytm, "PL1", ["aaaaaaaaaaa", "bbbbbbbbbbb"])
    assert moves == 0
    assert ytm.moves == []


def test_reorder_swaps_two_items():
    ytm = FakeYTM(
        playlist={
            "tracks": [
                {"videoId": "aaaaaaaaaaa", "setVideoId": "s1"},
                {"videoId": "bbbbbbbbbbb", "setVideoId": "s2"},
            ]
        }
    )
    moves = _reorder_playlist(ytm, "PL1", ["bbbbbbbbbbb", "aaaaaaaaaaa"])
    assert moves == 1
    assert len(ytm.moves) == 1


def test_invalid_video_ids_error_message():
    err = InvalidVideoIDsError(["a", "b"])
    assert err.invalid_ids == ["a", "b"]
    assert "2 invalid" in str(err)
