from src.cache.playlist import PlaylistCache


def _pc(tmp_path):
    return PlaylistCache(str(tmp_path / ".playlist_cache.json"))


def test_set_and_get_template(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("My Playlist", "PL123", ["a", "b", "c"])
    assert pc.get_id("My Playlist") == "PL123"
    assert pc.get_template("My Playlist") == ["a", "b", "c"]


def test_get_id_miss_returns_none(tmp_path):
    assert _pc(tmp_path).get_id("Unknown") is None


def test_get_template_empty_returns_none(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("Empty", "PL0", [])
    assert pc.get_template("Empty") is None


def test_template_changed_when_uncached(tmp_path):
    pc = _pc(tmp_path)
    assert pc.template_changed("New", ["a"]) is True


def test_template_unchanged_for_identical_ids(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("P", "PL1", ["a", "b"])
    assert pc.template_changed("P", ["a", "b"]) is False


def test_template_changed_for_reordering(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("P", "PL1", ["a", "b"])
    assert pc.template_changed("P", ["b", "a"]) is True


def test_touch_updates_timestamp_only(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("P", "PL1", ["a", "b"])
    before = pc._cache["P"]["last_updated"]
    pc._cache["P"]["last_updated"] = "2000-01-01T00:00:00+00:00"
    pc.touch("P")
    after = pc._cache["P"]["last_updated"]
    assert after != "2000-01-01T00:00:00+00:00"
    assert pc.get_template("P") == ["a", "b"]
    assert before != "2000-01-01T00:00:00+00:00"


def test_touch_missing_playlist_is_noop(tmp_path):
    pc = _pc(tmp_path)
    pc.touch("Missing")
    assert pc.get_id("Missing") is None


def test_remove(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("P", "PL1", ["a"])
    pc.remove("P")
    assert pc.get_id("P") is None


def test_remove_video_id(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("P", "PL1", ["a", "b", "c"])
    assert pc.remove_video_id("P", "b") is True
    assert pc.get_video_ids("P") == ["a", "c"]


def test_remove_video_id_not_present(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("P", "PL1", ["a"])
    assert pc.remove_video_id("P", "z") is False
    assert pc.remove_video_id("Missing", "a") is False


def test_get_video_ids_returns_copy(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("P", "PL1", ["a", "b"])
    ids = pc.get_video_ids("P")
    ids.append("mutated")
    assert pc.get_video_ids("P") == ["a", "b"]


def test_summary_sorted_with_counts(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("Zebra", "PL2", ["a", "b"])
    pc.set_template("apple", "PL1", ["x"])
    summary = pc.summary()
    assert [s["name"] for s in summary] == ["apple", "Zebra"]
    assert summary[0]["video_count"] == 1
    assert summary[1]["video_count"] == 2


def test_prune_old_weeklies_keeps_newest(tmp_path):
    pc = _pc(tmp_path)
    prefix = "Recents"
    for d in ("2024-01-01", "2024-01-08", "2024-01-15"):
        pc.set_template(f"{prefix} week of {d}", f"PL{d}", ["a"])
    removed = pc.prune_old_weeklies(prefix, keep_count=1)
    assert removed == ["Recents week of 2024-01-08", "Recents week of 2024-01-01"]
    assert pc.get_id("Recents week of 2024-01-15") is not None


def test_prune_old_weeklies_noop_when_within_keep(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("Recents week of 2024-01-15", "PL1", ["a"])
    assert pc.prune_old_weeklies("Recents", keep_count=2) == []


def test_clear_old_weekly_songs_keeps_ids_drops_songs(tmp_path):
    pc = _pc(tmp_path)
    prefix = "Recents"
    for d in ("2024-01-01", "2024-01-08", "2024-01-15"):
        pc.set_template(f"{prefix} week of {d}", f"PL{d}", ["a", "b"])
    current = f"{prefix} week of 2024-01-15"
    cleared = pc.clear_old_weekly_songs(prefix, current)
    assert set(cleared) == {"Recents week of 2024-01-01", "Recents week of 2024-01-08"}
    assert pc.get_id("Recents week of 2024-01-01") == "PL2024-01-01"
    assert pc.get_video_ids("Recents week of 2024-01-01") == []
    assert pc.get_video_ids(current) == ["a", "b"]


def test_persists_across_instances(tmp_path):
    path = str(tmp_path / ".playlist_cache.json")
    PlaylistCache(path).set_template("P", "PL1", ["a", "b"])
    assert PlaylistCache(path).get_template("P") == ["a", "b"]
