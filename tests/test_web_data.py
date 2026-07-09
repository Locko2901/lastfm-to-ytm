"""Unit tests for ``web.services.data`` - the web dashboard's data layer.

Covers the pure, file-backed data-shaping logic that powers the dashboard
panels, run against the hermetic ``web_paths`` / ``flask_app`` fixtures. See
the "What the web tests deliberately skip" section in ``docs/testing.md`` for
the full list of what is and isn't covered here, and why.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

pytest.importorskip("flask")

from src.cache.search import SearchCache, SearchOverrides
from src.cache.tags import TagCache, TagOverrides
from web.services import data


def _search_cache(web_paths) -> SearchCache:
    return SearchCache(str(web_paths["SEARCH_CACHE_FILE"]))


def _overrides(web_paths) -> SearchOverrides:
    return SearchOverrides(str(web_paths["OVERRIDES_FILE"]))


def _tag_cache(web_paths) -> TagCache:
    return TagCache(str(web_paths["TAG_CACHE_FILE"]))


def _tag_overrides(web_paths) -> TagOverrides:
    return TagOverrides(str(web_paths["TAG_OVERRIDES_FILE"]))


def test_get_cache_stats_counts_found_and_not_found(flask_app, web_paths):
    sc = _search_cache(web_paths)
    sc.set("Artist A", "Song A", "vidAAAAAAAA")
    sc.set("Artist B", "Song B", None)

    with flask_app.app_context():
        stats = data.get_cache_stats()

    assert stats == {"total": 2, "found": 1, "not_found": 1}


def test_get_not_found_tracks_sorted_desc_by_timestamp(flask_app, web_paths):
    now = datetime.now(UTC)
    older = (now - timedelta(hours=2)).isoformat()
    newer = now.isoformat()

    web_paths["SEARCH_CACHE_FILE"].write_text(
        json.dumps(
            {
                "a|old": {"artist": "A", "title": "old", "video_id": None, "timestamp": older},
                "b|new": {"artist": "B", "title": "new", "video_id": None, "timestamp": newer},
                "c|found": {"artist": "C", "title": "found", "video_id": "vidCCCCCCCC", "timestamp": newer},
            }
        )
    )

    with flask_app.app_context():
        result = data.get_not_found_tracks()

    assert [r["title"] for r in result] == ["new", "old"]


def test_get_cached_tracks_annotates_override_and_blacklist(flask_app, web_paths):
    sc = _search_cache(web_paths)
    sc.set("Artist A", "Song A", "vidAAAAAAAA", yt_title="Song A (Official)")
    sc.set("Artist B", "Song B", "vidBBBBBBBB")
    sc.set("Missing", "NoVid", None)

    ov = _overrides(web_paths)
    ov.set("Artist A", "Song A", "vidAAAAAAAA", reason="manual")
    ov.blacklist("Artist B", "Song B", reason="bad")

    with flask_app.app_context():
        tracks = {t["title"]: t for t in data.get_cached_tracks()}

    assert "NoVid" not in tracks
    assert tracks["Song A"]["has_override"] is True
    assert tracks["Song A"]["is_blacklisted"] is False
    assert tracks["Song B"]["has_override"] is False
    assert tracks["Song B"]["is_blacklisted"] is True


def test_get_overrides_data_splits_overrides_and_blacklist(flask_app, web_paths):
    ov = _overrides(web_paths)
    ov.set("Artist A", "Song A", "vidAAAAAAAA", reason="wrong version")
    ov.blacklist("Artist B", "Song B", reason="live only")

    with flask_app.app_context():
        overrides, blacklist = data.get_overrides_data()

    assert len(overrides) == 1
    assert overrides[0]["video_id"] == "vidAAAAAAAA"
    assert overrides[0]["reason"] == "wrong version"
    assert len(blacklist) == 1
    assert blacklist[0]["reason"] == "live only"


def test_load_run_log_missing_returns_empty(flask_app):
    with flask_app.app_context():
        log = data.load_run_log()

    assert log == {
        "mappings": [],
        "limit": 100,
        "timestamp": None,
        "total": 0,
        "resolved": 0,
        "in_playlist": 0,
    }


def test_load_run_log_enriches_from_cache_and_overrides(flask_app, web_paths):
    sc = _search_cache(web_paths)
    sc.set("Cached Artist", "Cached Song", "vidCACHEDXX", yt_title="Cached (Official)")

    ov = _overrides(web_paths)
    ov.set("Over Artist", "Over Song", "vidOVERRIDE0")

    run_log = {
        "timestamp": "2025-01-01T00:00:00",
        "total": 3,
        "mappings": [
            {"artist": "Cached Artist", "title": "Cached Song", "source": "cache"},
            {"artist": "Over Artist", "title": "Over Song", "source": "override"},
            {"artist": "Unknown", "title": "Pending", "source": "search"},  # not in cache -> pending_retry
        ],
    }
    web_paths["RUN_LOG_FILE"].write_text(json.dumps(run_log))

    with flask_app.app_context():
        result = data.load_run_log()

    by_title = {m["title"]: m for m in result["mappings"]}
    assert by_title["Cached Song"]["video_id"] == "vidCACHEDXX"
    assert by_title["Cached Song"]["yt_title"] == "Cached (Official)"
    assert by_title["Over Song"]["video_id"] == "vidOVERRIDE0"
    assert by_title["Pending"]["video_id"] is None
    assert by_title["Pending"]["pending_retry"] is True
    assert result["resolved"] == 2
    assert result["in_playlist"] == 3
    assert result["total"] == 3


def test_get_playlist_mappings_filters_and_annotates(flask_app, web_paths):
    sc = _search_cache(web_paths)
    sc.set("Cached Artist", "Cached Song", "vidCACHEDXX")

    ov = _overrides(web_paths)
    ov.set("Cached Artist", "Cached Song", "vidCACHEDXX")

    run_log = {
        "timestamp": "2025-01-01T00:00:00",
        "total": 2,
        "mappings": [
            {"artist": "Cached Artist", "title": "Cached Song", "source": "cache"},
            {"artist": "Nope", "title": "Unresolved", "source": "search"},
        ],
    }
    web_paths["RUN_LOG_FILE"].write_text(json.dumps(run_log))

    with flask_app.app_context():
        mappings, _run = data.get_playlist_mappings()

    titles = {m["title"] for m in mappings}
    assert "Cached Song" in titles
    resolved = next(m for m in mappings if m["title"] == "Cached Song")
    assert resolved["is_overridden"] is True
    assert resolved["ytm_url"] == "https://music.youtube.com/watch?v=vidCACHEDXX"


def test_failure_log_load_and_clear(flask_app, web_paths):
    with flask_app.app_context():
        assert data.load_failure_log() is None
        assert data.clear_failure_log() is False

    web_paths["FAILURE_LOG_FILE"].write_text(json.dumps({"error": "boom"}))

    with flask_app.app_context():
        assert data.load_failure_log() == {"error": "boom"}
        assert data.clear_failure_log() is True
        assert data.load_failure_log() is None


def test_get_playlist_links_main_and_weekly(flask_app, web_paths):
    cache_data = {
        "Last.fm Recents (auto)": {"id": "MAINID"},
        "Last.fm Recents week of 2025-01-06": {"id": "WK1"},
        "Last.fm Recents week of 2025-01-13": {"id": "WK2"},
    }
    web_paths["PLAYLIST_CACHE_FILE"].write_text(json.dumps(cache_data))

    with flask_app.app_context():
        links = data.get_playlist_links()

    assert links["main_url"] == "https://music.youtube.com/playlist?list=MAINID"
    assert links["weekly_enabled"] is True
    assert links["weekly_url"] == "https://music.youtube.com/playlist?list=WK2"
    assert links["weekly_name"] == "Last.fm Recents week of 2025-01-13"


def test_get_playlist_links_missing_cache(flask_app):
    with flask_app.app_context():
        links = data.get_playlist_links()

    assert links["main_url"] is None
    assert links["weekly_url"] is None


def test_get_setup_status_needs_setup_when_no_env(flask_app):
    with flask_app.app_context():
        status = data.get_setup_status()

    assert status["needs_setup"] is True
    assert status["has_env"] is False
    assert status["has_browser_json"] is False


def test_get_setup_status_with_user_config_and_browser(flask_app, web_paths):
    web_paths["ENV_FILE"].write_text("LASTFM_USER=bob\n# a comment\n")
    web_paths["BROWSER_JSON_FILE"].write_text('{"cookie": "long-enough-value"}')

    with flask_app.app_context():
        status = data.get_setup_status()

    assert status["needs_setup"] is False
    assert status["has_env"] is True
    assert status["has_browser_json"] is True
    assert status["needs_auth"] is False


def test_env_has_user_config_ignores_auto_keys(web_paths):
    web_paths["ENV_FILE"].write_text("FLASK_SECRET_KEY=abc123\n")
    assert data._env_has_user_config(web_paths["ENV_FILE"]) is False

    web_paths["ENV_FILE"].write_text("FLASK_SECRET_KEY=abc\nLASTFM_USER=bob\n")
    assert data._env_has_user_config(web_paths["ENV_FILE"]) is True


def test_tag_cache_tracks_and_overrides(flask_app, web_paths):
    tc = _tag_cache(web_paths)
    tc.set("Rock Artist", "Rock Song", [{"name": "rock", "count": 80}, {"name": "rare", "count": 2}])

    to = _tag_overrides(web_paths)
    to.set("Pop Artist", "Pop Song", ["pop"], mode="replace", reason="fix")

    with flask_app.app_context():
        tracks = {t["title"]: t for t in data.get_tag_cache_tracks()}
        override_data = data.get_tag_overrides_data()
        tag_map = data.get_track_tags_map()
        suggestions = data.get_tag_suggestions()

    assert "rock" in tracks["Rock Song"]["lastfm_tags"]
    assert tracks["Pop Song"]["has_override"] is True
    assert tracks["Pop Song"]["override_mode"] == "replace"

    assert len(override_data) == 1
    assert override_data[0]["mode"] == "replace"

    rock_key = "rock artist|rock song"
    assert tag_map[rock_key] == ["rock"]
    assert "rock" in suggestions
    assert "pop" in suggestions


def test_custom_playlists_config_round_trip(flask_app, web_paths):
    payload = [
        {
            "name": "Chill",
            "description": "calm tracks",
            "tags": ["ambient", "chill"],
            "match": "any",
            "limit": 25,
            "blacklist": ["bad artist|bad song"],
            "backfill": True,
            "auto_sync": False,
        }
    ]

    with flask_app.app_context():
        data.save_custom_playlists_config(payload)

    assert web_paths["CUSTOM_PLAYLISTS_FILE"].exists()
    saved = json.loads(web_paths["CUSTOM_PLAYLISTS_FILE"].read_text())
    assert saved["playlists"][0]["name"] == "Chill"

    with flask_app.app_context():
        loaded = data.load_custom_playlists_config()

    assert len(loaded) == 1
    cfg = loaded[0]
    assert cfg["name"] == "Chill"
    assert cfg["tags"] == ["ambient", "chill"]
    assert cfg["auto_sync"] is False
    assert cfg["track_count"] == 0
    assert cfg["playlist_id"] is None


def test_get_custom_playlist_tracks_resolves_video_ids(flask_app, web_paths):
    cfg = [{"name": "Chill", "tags": ["chill"], "blacklist": []}]
    web_paths["CUSTOM_PLAYLISTS_FILE"].write_text(json.dumps({"playlists": cfg}))

    web_paths["PLAYLIST_CACHE_FILE"].write_text(json.dumps({"Chill": {"id": "PLID", "video_ids": ["vidCHILL0001"]}}))

    sc = _search_cache(web_paths)
    sc.set("Chill Artist", "Chill Song", "vidCHILL0001", yt_title="Chill (Official)")

    with flask_app.app_context():
        tracks = data.get_custom_playlist_tracks(0)

    assert len(tracks) == 1
    assert tracks[0]["artist"] == "Chill Artist"
    assert tracks[0]["video_id"] == "vidCHILL0001"
    assert tracks[0]["ytm_url"] == "https://music.youtube.com/watch?v=vidCHILL0001"


def test_get_custom_playlist_tracks_invalid_index(flask_app):
    with flask_app.app_context():
        assert data.get_custom_playlist_tracks(5) == []


def _export_tracks() -> list[dict[str, object]]:
    return [
        {"artist": "Boards of Canada", "title": "Roygbiv", "video_id": "vidROYGBIV01", "yt_title": "Roygbiv (Official)"},
        {"artist": "Aphex Twin", "title": "Xtal", "video_id": "vidXTAL00001", "yt_title": None},
    ]


def test_render_export_json_shape():
    from web.services.export import render_export

    body, mimetype, ext = render_export("My List", _export_tracks(), "json")
    assert mimetype == "application/json"
    assert ext == "json"
    payload = json.loads(body)
    assert payload["playlist"] == "My List"
    assert payload["track_count"] == 2
    assert payload["tracks"][0]["url"] == "https://music.youtube.com/watch?v=vidROYGBIV01"


def test_render_export_csv_has_header_and_rows():
    from web.services.export import render_export

    body, mimetype, ext = render_export("My List", _export_tracks(), "csv")
    assert mimetype == "text/csv"
    assert ext == "csv"
    lines = body.strip().splitlines()
    assert lines[0] == "artist,title,video_id,yt_title,url"
    assert "Boards of Canada" in lines[1]
    assert len(lines) == 3


def test_render_export_m3u_extinf_lines():
    from web.services.export import render_export

    body, mimetype, ext = render_export("My List", _export_tracks(), "m3u")
    assert mimetype == "audio/x-mpegurl"
    assert ext == "m3u8"
    assert body.startswith("#EXTM3U")
    assert "#PLAYLIST:My List" in body
    assert "#EXTINF:-1,Boards of Canada - Roygbiv" in body
    assert "https://music.youtube.com/watch?v=vidXTAL00001" in body


def test_render_export_unknown_format_returns_none():
    from web.services.export import render_export

    assert render_export("My List", _export_tracks(), "xml") is None


def test_get_discovery_seed_options_from_search_cache(flask_app, web_paths, monkeypatch):
    monkeypatch.setattr(data, "get_local_scrobble_db", lambda: None)
    sc = _search_cache(web_paths)
    sc.set("Boards of Canada", "Roygbiv", "vidROYGBIV01")
    sc.set("Aphex Twin", "Xtal", "vidXTAL00001")
    sc.set("Aphex Twin", "Windowlicker", "vidWINDOW001")

    with flask_app.app_context():
        options = data.get_discovery_seed_options()

    assert options["source"] == "search_cache"
    assert options["artists"] == ["Aphex Twin", "Boards of Canada"]
    track_pairs = {(t["artist"], t["title"]) for t in options["tracks"]}
    assert ("Boards of Canada", "Roygbiv") in track_pairs
    assert ("Aphex Twin", "Xtal") in track_pairs
    assert len(options["tracks"]) == 3


def test_get_discovery_seed_options_from_local_db(flask_app, monkeypatch):
    class _FakeDB:
        def get_scoring_rows(self, min_plays=1):  # noqa: ARG002
            return [
                ("Radiohead", "Idioteque", "Kid A", 50, 0, 0),
                ("Radiohead", "Everything In Its Right Place", "Kid A", 30, 0, 0),
                ("Aphex Twin", "Xtal", "SAW 85-92", 20, 0, 0),
            ]

    monkeypatch.setattr(data, "get_local_scrobble_db", _FakeDB)

    with flask_app.app_context():
        options = data.get_discovery_seed_options()

    assert options["source"] == "local_db"
    assert options["artists"] == ["Radiohead", "Aphex Twin"]
    assert options["tracks"][0] == {"artist": "Radiohead", "title": "Idioteque"}
    assert len(options["tracks"]) == 3
