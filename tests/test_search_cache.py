from datetime import UTC, datetime, timedelta

from src.cache.search import NOT_FOUND, SearchCache


def _make_cache(tmp_path, **kwargs) -> SearchCache:
    return SearchCache(str(tmp_path / ".search_cache.json"), **kwargs)


def test_set_and_get_roundtrip(tmp_path):
    cache = _make_cache(tmp_path)
    cache.set("Daft Punk", "One More Time", "abc123")
    assert cache.get("Daft Punk", "One More Time") == "abc123"


def test_get_is_case_insensitive(tmp_path):
    cache = _make_cache(tmp_path)
    cache.set("Daft Punk", "One More Time", "abc123")
    assert cache.get("daft punk", "ONE MORE TIME") == "abc123"


def test_get_missing_returns_none(tmp_path):
    cache = _make_cache(tmp_path)
    assert cache.get("Unknown", "Track") is None


def test_negative_cache_returns_sentinel(tmp_path):
    cache = _make_cache(tmp_path)
    cache.set("Obscure", "B-side", None)
    assert cache.get("Obscure", "B-side") == NOT_FOUND


def test_negative_cache_skipped_when_ttl_zero(tmp_path):
    cache = _make_cache(tmp_path, notfound_ttl_days=0)
    cache.set("Obscure", "B-side", None)
    assert cache.get("Obscure", "B-side") is None


def test_make_key_format(tmp_path):
    cache = _make_cache(tmp_path)
    assert cache._make_key("Artist Name", "Song Title") == "artist name|song title"


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / ".search_cache.json")
    SearchCache(path).set("Artist", "Title", "vid999")
    assert SearchCache(path).get("Artist", "Title") == "vid999"


def test_delete_by_track(tmp_path):
    cache = _make_cache(tmp_path)
    cache.set("Artist", "Title", "vid")
    assert cache.delete_by_track("Artist", "Title") is True
    assert cache.get("Artist", "Title") is None
    assert cache.delete_by_track("Artist", "Title") is False


def test_get_entry_includes_yt_title(tmp_path):
    cache = _make_cache(tmp_path)
    cache.set("Artist", "Title", "vid", yt_title="Artist - Title (Official)")
    entry = cache.get_entry("Artist", "Title")
    assert entry is not None
    assert entry["yt_title"] == "Artist - Title (Official)"


def test_expired_positive_entry_removed_on_load(tmp_path):
    path = str(tmp_path / ".search_cache.json")
    cache = SearchCache(path, ttl_days=30)
    cache.set("Artist", "Title", "vid")
    old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    cache._cache[cache._make_key("Artist", "Title")]["timestamp"] = old
    cache._save()
    assert SearchCache(path, ttl_days=30).get("Artist", "Title") is None


def test_expired_notfound_entry_removed_on_load(tmp_path):
    path = str(tmp_path / ".search_cache.json")
    cache = SearchCache(path, notfound_ttl_days=7)
    cache.set("Artist", "Title", None)
    old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    cache._cache[cache._make_key("Artist", "Title")]["timestamp"] = old
    cache._save()
    assert SearchCache(path, notfound_ttl_days=7).get("Artist", "Title") is None


def test_clear_notfound(tmp_path):
    cache = _make_cache(tmp_path)
    cache.set("A", "found", "vid")
    cache.set("B", "missing", None)
    assert cache.clear_notfound() == 1
    assert cache.get("A", "found") == "vid"
    assert cache.get("B", "missing") is None
