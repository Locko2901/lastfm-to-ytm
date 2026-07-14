"""Tests for playlist rename detection (get_or_rename_playlist)."""

from src.cache.playlist import PlaylistCache
from src.ytm.operations import (
    create_playlist_with_items,
    get_existing_playlist_by_name,
    get_or_rename_playlist,
)


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


def test_library_scan_reconciles_stale_id_with_empty_template(tmp_path):
    pc = _pc(tmp_path)
    pc.track_id("Weekly week of 2026-06-22", "PL_stale")
    ytm = _FakeYTM(
        library=[{"title": "Weekly week of 2026-06-22", "playlistId": "PL_canonical"}],
        existing_ids=["PL_canonical"],
    )
    result = get_existing_playlist_by_name(ytm, "Weekly week of 2026-06-22", cache=pc)
    assert result == "PL_canonical"
    assert pc.get_id("Weekly week of 2026-06-22") == "PL_canonical"


class _CreatingYTM:
    """Fake that returns a compact ID on create and the canonical ID on get_playlist."""

    def __init__(self, short_id, canonical_id):
        self._short = short_id
        self._canonical = canonical_id
        self.created: list[str] = []

    def create_playlist(self, title, description, privacy_status="PRIVATE", video_ids=None, **_kwargs):  # noqa: ARG002
        self.created.append(title)
        return self._short

    def get_playlist(self, playlist_id, limit=None):  # noqa: ARG002
        return {"id": self._canonical}


def test_create_resolves_and_caches_canonical_id(tmp_path):
    pc = _pc(tmp_path)
    ytm = _CreatingYTM(short_id="PLshort", canonical_id="PLnXjAqoyEY4canonical")
    returned = create_playlist_with_items(ytm, "New PL", "desc", "PRIVATE", ["a", "b"], cache=pc, role="main")
    assert returned == "PLnXjAqoyEY4canonical"
    assert pc.get_id("New PL") == "PLnXjAqoyEY4canonical"
    assert pc.find_by_role("main") == ("New PL", "PLnXjAqoyEY4canonical")


def test_create_falls_back_to_create_id_when_resolution_fails(tmp_path):
    pc = _pc(tmp_path)

    class _FailingResolve(_CreatingYTM):
        def get_playlist(self, playlist_id, limit=None):  # noqa: ARG002
            raise RuntimeError("transient")

    ytm = _FailingResolve(short_id="PLshort", canonical_id="unused")
    returned = create_playlist_with_items(ytm, "New PL", "desc", "PRIVATE", ["a"], cache=pc, max_retries=1)
    assert returned == "PLshort"
    assert pc.get_id("New PL") == "PLshort"


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
