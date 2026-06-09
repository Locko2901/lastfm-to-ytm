from datetime import UTC, datetime, timedelta

from src.cache.tags import TagCache, TagOverrides

SAMPLE_TAGS = [{"name": "rock", "count": 100}, {"name": "indie", "count": 50}]


def _tag_cache(tmp_path, **kwargs):
    return TagCache(str(tmp_path / ".tag_cache.json"), **kwargs)


def _tag_overrides(tmp_path):
    return TagOverrides(str(tmp_path / "tag_overrides.json"))


def test_set_and_get_roundtrip(tmp_path):
    tc = _tag_cache(tmp_path)
    tc.set("Artist", "Title", SAMPLE_TAGS)
    assert tc.get("Artist", "Title") == SAMPLE_TAGS


def test_get_is_case_insensitive(tmp_path):
    tc = _tag_cache(tmp_path)
    tc.set("Artist", "Title", SAMPLE_TAGS)
    assert tc.get("artist", "TITLE") == SAMPLE_TAGS


def test_get_missing_returns_none(tmp_path):
    assert _tag_cache(tmp_path).get("Nope", "Nope") is None


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / ".tag_cache.json")
    TagCache(path).set("Artist", "Title", SAMPLE_TAGS)
    assert TagCache(path).get("Artist", "Title") == SAMPLE_TAGS


def test_expired_entry_removed_on_load(tmp_path):
    path = str(tmp_path / ".tag_cache.json")
    tc = TagCache(path, ttl_days=90)
    tc.set("Artist", "Title", SAMPLE_TAGS)
    old = (datetime.now(UTC) - timedelta(days=91)).isoformat()
    tc._cache[tc._make_key("Artist", "Title")]["timestamp"] = old
    tc._save()
    assert TagCache(path, ttl_days=90).get("Artist", "Title") is None


def test_delete_by_track(tmp_path):
    tc = _tag_cache(tmp_path)
    tc.set("Artist", "Title", SAMPLE_TAGS)
    assert tc.delete_by_track("Artist", "Title") is True
    assert tc.get("Artist", "Title") is None
    assert tc.delete_by_track("Artist", "Title") is False


def test_delete_keys_counts_removed(tmp_path):
    tc = _tag_cache(tmp_path)
    tc.set("A", "1", SAMPLE_TAGS)
    tc.set("B", "2", SAMPLE_TAGS)
    deleted = tc.delete_keys([tc._make_key("A", "1"), "missing|key"])
    assert deleted == 1
    assert tc.get("A", "1") is None
    assert tc.get("B", "2") == SAMPLE_TAGS


def test_stats(tmp_path):
    tc = _tag_cache(tmp_path)
    tc.set("A", "1", SAMPLE_TAGS)
    tc.set("B", "2", [])
    assert tc.stats() == {"total": 2, "with_tags": 1, "empty": 1}


def test_overrides_set_and_get(tmp_path):
    ov = _tag_overrides(tmp_path)
    ov.set("Artist", "Title", ["Rock", "Indie"], mode="add")
    result = ov.get("Artist", "Title")
    assert result is not None
    tags, mode = result
    assert mode == "add"
    assert {t["name"] for t in tags} == {"rock", "indie"}


def test_overrides_get_missing_returns_none(tmp_path):
    assert _tag_overrides(tmp_path).get("Nope", "Nope") is None


def test_apply_replace_mode_discards_api_tags(tmp_path):
    ov = _tag_overrides(tmp_path)
    ov.set("Artist", "Title", ["jazz"], mode="replace")
    result = ov.apply("Artist", "Title", [{"name": "pop", "count": 10}])
    assert [t["name"] for t in result] == ["jazz"]


def test_apply_add_mode_merges_without_duplicates(tmp_path):
    ov = _tag_overrides(tmp_path)
    ov.set("Artist", "Title", ["rock"], mode="add")
    api = [{"name": "rock", "count": 10}, {"name": "pop", "count": 5}]
    result = ov.apply("Artist", "Title", api)
    names = [t["name"] for t in result]
    assert names.count("rock") == 1
    assert "pop" in names


def test_apply_no_override_returns_api_tags(tmp_path):
    ov = _tag_overrides(tmp_path)
    api = [{"name": "pop", "count": 5}]
    assert ov.apply("Artist", "Title", api) == api


def test_overrides_remove(tmp_path):
    ov = _tag_overrides(tmp_path)
    ov.set("Artist", "Title", ["rock"])
    assert ov.remove("Artist", "Title") is True
    assert ov.get("Artist", "Title") is None
    assert ov.remove("Artist", "Title") is False


def test_overrides_persist_across_instances(tmp_path):
    path = str(tmp_path / "tag_overrides.json")
    TagOverrides(path).set("Artist", "Title", ["rock"], mode="replace")
    result = TagOverrides(path).get("Artist", "Title")
    assert result is not None
    assert result[1] == "replace"
