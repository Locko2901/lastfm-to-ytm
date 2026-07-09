"""Unit tests for the pure sync-preview (dry run) diff builder."""

from __future__ import annotations

from src.playlist.preview import build_sync_preview


def _current(*pairs: tuple[str, str, str]) -> list[dict[str, str]]:
    return [{"video_id": vid, "title": title, "artist": artist} for vid, title, artist in pairs]


def test_preview_new_playlist_all_added() -> None:
    resolved = {
        "vidAAAAAAAA": {"artist": "A", "title": "Song A", "score": 0.9, "plays": 5, "source": "cache"},
        "vidBBBBBBBB": {"artist": "B", "title": "Song B", "score": 0.8, "plays": 3, "source": "search"},
    }
    preview = build_sync_preview(
        playlist_name="My Playlist",
        playlist_id=None,
        current_tracks=[],
        desired_video_ids=["vidAAAAAAAA", "vidBBBBBBBB"],
        resolved_details=resolved,
        misses=1,
    )

    assert preview["exists"] is False
    assert preview["summary"] == {
        "current_count": 0,
        "desired_count": 2,
        "added": 2,
        "removed": 0,
        "unchanged": 0,
        "reordered": False,
    }
    assert preview["misses"] == 1
    assert [t["video_id"] for t in preview["added"]] == ["vidAAAAAAAA", "vidBBBBBBBB"]
    assert preview["added"][0]["score"] == 0.9
    assert preview["added"][0]["plays"] == 5
    assert preview["removed"] == []


def test_preview_adds_and_removes() -> None:
    current = _current(
        ("vidAAAAAAAA", "Song A", "A"),
        ("vidCCCCCCCC", "Song C", "C"),
    )
    resolved = {
        "vidAAAAAAAA": {"artist": "A", "title": "Song A", "score": 0.9, "plays": 5, "source": "cache"},
        "vidBBBBBBBB": {"artist": "B", "title": "Song B", "score": 0.8, "plays": 3, "source": "search"},
    }
    preview = build_sync_preview(
        playlist_name="My Playlist",
        playlist_id="PL123",
        current_tracks=current,
        desired_video_ids=["vidAAAAAAAA", "vidBBBBBBBB"],
        resolved_details=resolved,
    )

    assert preview["exists"] is True
    assert preview["summary"]["added"] == 1
    assert preview["summary"]["removed"] == 1
    assert preview["summary"]["unchanged"] == 1
    assert [t["video_id"] for t in preview["added"]] == ["vidBBBBBBBB"]
    removed = preview["removed"]
    assert len(removed) == 1
    assert removed[0]["video_id"] == "vidCCCCCCCC"
    assert removed[0]["title"] == "Song C"


def test_preview_detects_pure_reorder() -> None:
    current = _current(
        ("vidAAAAAAAA", "Song A", "A"),
        ("vidBBBBBBBB", "Song B", "B"),
    )
    preview = build_sync_preview(
        playlist_name="My Playlist",
        playlist_id="PL123",
        current_tracks=current,
        desired_video_ids=["vidBBBBBBBB", "vidAAAAAAAA"],
        resolved_details={},
    )

    assert preview["summary"]["added"] == 0
    assert preview["summary"]["removed"] == 0
    assert preview["summary"]["unchanged"] == 2
    assert preview["summary"]["reordered"] is True


def test_preview_no_changes_when_identical() -> None:
    current = _current(
        ("vidAAAAAAAA", "Song A", "A"),
        ("vidBBBBBBBB", "Song B", "B"),
    )
    preview = build_sync_preview(
        playlist_name="My Playlist",
        playlist_id="PL123",
        current_tracks=current,
        desired_video_ids=["vidAAAAAAAA", "vidBBBBBBBB"],
        resolved_details={},
    )

    assert preview["summary"]["added"] == 0
    assert preview["summary"]["removed"] == 0
    assert preview["summary"]["reordered"] is False


def test_preview_missing_resolved_details_defaults() -> None:
    preview = build_sync_preview(
        playlist_name="P",
        playlist_id=None,
        current_tracks=[],
        desired_video_ids=["vidAAAAAAAA"],
        resolved_details={},
    )
    added = preview["added"][0]
    assert added["artist"] == ""
    assert added["title"] == ""
    assert added["score"] is None
    assert added["plays"] is None
