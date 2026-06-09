import json

from src.cache import JSONCache


def _cache(tmp_path, name=".cache.json"):
    c = JSONCache(str(tmp_path / name))
    c._load()
    return c


def test_load_missing_file_starts_empty(tmp_path):
    c = _cache(tmp_path)
    assert c.size() == 0


def test_save_and_reload_roundtrip(tmp_path):
    path = tmp_path / ".cache.json"
    c = JSONCache(str(path))
    c._load()
    c._cache["a"] = {"x": 1}
    c._save()

    fresh = JSONCache(str(path))
    fresh._load()
    assert fresh._cache == {"a": {"x": 1}}


def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    path = tmp_path / ".cache.json"
    c = JSONCache(str(path))
    c._load()
    c._cache["k"] = 1
    c._save()
    assert path.exists()
    assert not path.with_suffix(".tmp").exists()


def test_corrupted_file_resets_to_empty(tmp_path):
    path = tmp_path / ".cache.json"
    path.write_text("{ this is not valid json", encoding="utf-8")
    c = JSONCache(str(path))
    c._load()
    assert c._cache == {}


def test_clear_empties_and_persists(tmp_path):
    path = tmp_path / ".cache.json"
    c = JSONCache(str(path))
    c._load()
    c._cache.update({"a": 1, "b": 2})
    c._save()
    c.clear()
    assert c.size() == 0

    fresh = JSONCache(str(path))
    fresh._load()
    assert fresh._cache == {}


def test_save_records_write_metric(tmp_path):
    c = _cache(tmp_path)
    before = c.get_metrics().writes
    c._cache["k"] = 1
    c._save()
    assert c.get_metrics().writes == before + 1


def test_save_writes_indented_json(tmp_path):
    path = tmp_path / ".cache.json"
    c = JSONCache(str(path))
    c._load()
    c._cache["k"] = {"nested": True}
    c._save()
    assert len(path.read_text(encoding="utf-8").splitlines()) > 1
    assert json.loads(path.read_text(encoding="utf-8")) == {"k": {"nested": True}}
