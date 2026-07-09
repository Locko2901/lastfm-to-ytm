"""Tests for playlist rename detection (get_or_rename_playlist)."""

from src.cache.playlist import PlaylistCache
from src.ytm.operations import get_or_rename_playlist


class _FakeYTM:
    """Minimal YTMusic stand-in tracking edit/library calls."""

    def __init__(self, library=None, existing_ids=None):
        self._library = library or []
        self._existing_ids = set(existing_ids or [])
        self.edited: list[tuple[str, str]] = []

    def get_library_playlists(self, limit=1000):  # noqa: ARG002
        return self._library

    def get_playlist(self, playlist_id, limit=None):  # noqa: ARG002
        if playlist_id in self._existing_ids:
            return {"id": playlist_id}
        raise RuntimeError("Unable to find 'contents'")

    def edit_playlist(self, playlist_id, title=None, **_kwargs):
        self.edited.append((playlist_id, title))
        return {"status": "STATUS_SUCCEEDED"}


def _pc(tmp_path):
    return PlaylistCache(str(tmp_path / ".playlist_cache.json"))


def test_returns_existing_id_when_name_matches(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("Main", "PL1", ["a"], role="main")
    ytm = _FakeYTM(existing_ids=["PL1"])
    assert get_or_rename_playlist(ytm, "Main", cache=pc, role="main") == "PL1"
    assert ytm.edited == []


def test_detects_rename_and_edits_in_place(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("Old Name", "PL1", ["a", "b"], role="main")
    ytm = _FakeYTM(existing_ids=["PL1"])

    result = get_or_rename_playlist(ytm, "New Name", cache=pc, role="main")

    assert result == "PL1"
    assert ytm.edited == [("PL1", "New Name")]
    assert pc.get_id("New Name") == "PL1"
    assert pc.get_id("Old Name") is None
    assert pc.find_by_role("main") == ("New Name", "PL1")


def test_no_rename_when_role_missing(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("Old Name", "PL1", ["a"], role="main")
    ytm = _FakeYTM(existing_ids=["PL1"])
    assert get_or_rename_playlist(ytm, "New Name", cache=pc, role=None) is None
    assert ytm.edited == []


def test_stale_cache_entry_pruned_when_playlist_gone(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("Old Name", "PLGONE", ["a"], role="main")
    ytm = _FakeYTM(existing_ids=[])  # get_playlist raises -> gone

    assert get_or_rename_playlist(ytm, "New Name", cache=pc, role="main") is None
    assert ytm.edited == []
    assert pc.get_id("Old Name") is None


def test_ambiguous_role_does_not_rename(tmp_path):
    pc = _pc(tmp_path)
    pc.set_template("A", "PL1", ["a"], role="custom:dup")
    pc.set_template("B", "PL2", ["b"], role="custom:dup")
    ytm = _FakeYTM(existing_ids=["PL1", "PL2"])
    assert get_or_rename_playlist(ytm, "C", cache=pc, role="custom:dup") is None
    assert ytm.edited == []
