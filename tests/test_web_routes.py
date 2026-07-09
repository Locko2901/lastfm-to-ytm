"""Unit tests for the web dashboard's HTTP routes (``web.routes.api`` + ``actions``).

Exercises the file-backed JSON/redirect endpoints through Flask's
``test_client`` against the hermetic ``web_paths`` fixture. See the
"What the web tests deliberately skip" section in ``docs/testing.md`` for the
full list of what is and isn't covered here, and why.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("flask")

from src.cache.search import SearchCache, SearchOverrides
from src.cache.tags import TagCache


def test_cache_stats_endpoint(client, web_paths):
    sc = SearchCache(str(web_paths["SEARCH_CACHE_FILE"]))
    sc.set("A", "1", "vidAAAAAAAA")
    sc.set("B", "2", None)

    resp = client.get("/api/cache-stats")
    assert resp.status_code == 200
    assert resp.get_json() == {"total": 2, "found": 1, "not_found": 1}


def test_mappings_endpoint_empty(client):
    resp = client.get("/api/mappings")
    assert resp.status_code == 200
    assert resp.get_json()["mappings"] == []


def test_preview_result_empty(client):
    resp = client.get("/preview_result")
    assert resp.status_code == 200
    assert resp.get_json() == {"available": False}


def test_preview_result_returns_saved_preview(client, web_paths):
    import json as _json

    preview = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "kind": "main",
        "playlists": [
            {
                "playlist_name": "My Playlist",
                "playlist_id": "PL123",
                "exists": True,
                "summary": {"current_count": 1, "desired_count": 2, "added": 1, "removed": 0, "unchanged": 1, "reordered": False},
                "added": [{"video_id": "vidBBBBBBBB", "artist": "B", "title": "Song B", "score": 0.8, "plays": 2, "source": "search"}],
                "removed": [],
                "misses": 0,
            }
        ],
    }
    web_paths["DRY_RUN_PREVIEW_FILE"].write_text(_json.dumps(preview), encoding="utf-8")

    resp = client.get("/preview_result")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["available"] is True
    assert body["kind"] == "main"
    assert body["playlists"][0]["playlist_name"] == "My Playlist"
    assert body["playlists"][0]["summary"]["added"] == 1
    assert body["playlists"][0]["added"][0]["video_id"] == "vidBBBBBBBB"


def test_overrides_endpoint(client, web_paths):
    ov = SearchOverrides(str(web_paths["OVERRIDES_FILE"]))
    ov.set("A", "1", "vidAAAAAAAA", reason="r")
    ov.blacklist("B", "2", reason="bl")

    resp = client.get("/api/overrides")
    body = resp.get_json()
    assert len(body["overrides"]) == 1
    assert len(body["blacklist"]) == 1


def test_settings_completeness_endpoint(client, web_paths, monkeypatch):
    from web.services import env as env_mod

    monkeypatch.setattr(env_mod, "ENV_EXAMPLE_FILE", web_paths["ENV_FILE"].parent / ".env.example")
    web_paths["ENV_FILE"].write_text("A=1\n", encoding="utf-8")
    env_mod.ENV_EXAMPLE_FILE.write_text("A=1\nB=2\n", encoding="utf-8")

    resp = client.get("/api/settings/completeness")
    assert resp.status_code == 200
    assert resp.get_json()["missing_keys"] == ["B"]


def test_settings_reconcile_endpoint(client, web_paths, monkeypatch):
    from web.services import env as env_mod

    monkeypatch.setattr(env_mod, "ENV_EXAMPLE_FILE", web_paths["ENV_FILE"].parent / ".env.example")
    web_paths["ENV_FILE"].write_text("A=keep\n", encoding="utf-8")
    env_mod.ENV_EXAMPLE_FILE.write_text("A=default\nB=new # c\n", encoding="utf-8")

    resp = client.post("/api/settings/reconcile")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["imported"] == ["B"]
    assert "A=keep" in web_paths["ENV_FILE"].read_text(encoding="utf-8")


def test_stats_endpoint(client, web_paths):
    sc = SearchCache(str(web_paths["SEARCH_CACHE_FILE"]))
    sc.set("A", "1", "vidAAAAAAAA")

    resp = client.get("/api/stats")
    body = resp.get_json()
    assert body["cached"] == 1
    assert body["overrides"] == 0
    assert "last_sync" in body


def test_settings_get_returns_all_keys(client):
    resp = client.get("/api/settings")
    body = resp.get_json()
    assert "PLAYLIST_NAME" in body
    assert "DEDUPLICATE" in body
    assert isinstance(body["DEDUPLICATE"], bool)
    assert "USE_LOCAL_LASTFM_DB" in body
    assert isinstance(body["USE_LOCAL_LASTFM_DB"], bool)


def test_lastfm_db_status_disabled(client):
    resp = client.get("/api/lastfm-db/status")
    assert resp.status_code == 200
    assert resp.get_json() == {"enabled": False}


def test_lastfm_db_clear_disabled_returns_400(client, monkeypatch):
    from web.routes import api

    monkeypatch.setattr(api, "get_local_scrobble_db", lambda: None)
    resp = client.post("/api/lastfm-db/clear")
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_lastfm_db_export_import_roundtrip(client, monkeypatch, tmp_path):
    import io
    import time

    from src.lastfm import LocalScrobbleDB, Scrobble
    from web.routes import api

    now = int(time.time())
    db = LocalScrobbleDB(tmp_path / "lfm.db")
    db.ingest_scrobbles([Scrobble("A", "Hit", "", now), Scrobble("A", "Hit", "", now)])
    monkeypatch.setattr(api, "get_local_scrobble_db", lambda: db)

    export = client.get("/api/lastfm-db/export")
    assert export.status_code == 200
    assert "attachment" in export.headers["Content-Disposition"]
    dump = export.get_data()

    db2 = LocalScrobbleDB(tmp_path / "lfm2.db")
    monkeypatch.setattr(api, "get_local_scrobble_db", lambda: db2)
    resp = client.post(
        "/api/lastfm-db/import",
        data={"file": (io.BytesIO(dump), "dump.json"), "mode": "merge"},
        content_type="multipart/form-data",
    )
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["imported"] == 1
    assert db2.get_total_plays() == 2


def test_history_status_does_not_clobber_total_tracks(client, monkeypatch, tmp_path):
    import time

    from src.lastfm import LocalScrobbleDB, Scrobble
    from web.routes import api

    class _FakeHistoryDB:
        def get_overview_stats(self):
            return {"total_tracks": 5, "found_tracks": 3, "not_found_tracks": 2, "total_syncs": 1}

        def get_db_size_bytes(self):
            return 100

        def get_near_miss_count(self):
            return 0

    now = int(time.time())
    local = LocalScrobbleDB(tmp_path / "lfm.db")
    local.ingest_scrobbles([Scrobble("A", "Hit", "", now), Scrobble("A", "Hit", "", now), Scrobble("B", "Deep", "", now)])

    monkeypatch.setattr(api, "is_history_enabled", lambda: True)
    monkeypatch.setattr(api, "get_history_db", _FakeHistoryDB)
    monkeypatch.setattr(api, "get_local_scrobble_db", lambda: local)

    body = client.get("/api/history/status").get_json()
    assert body["total_tracks"] == 5
    assert body["found_tracks"] + body["not_found_tracks"] == body["total_tracks"]
    assert body["local_lastfm_enabled"] is True
    assert body["library_tracks"] == 2
    assert body["library_plays"] == 3
    assert "total_plays" not in body


def test_history_status_without_local_lastfm(client, monkeypatch):
    """Only History DB enabled: no library_* keys, local flag False."""
    from web.routes import api

    class _FakeHistoryDB:
        def get_overview_stats(self):
            return {"total_tracks": 5, "found_tracks": 3, "not_found_tracks": 2, "total_syncs": 1}

        def get_db_size_bytes(self):
            return 100

        def get_near_miss_count(self):
            return 0

    monkeypatch.setattr(api, "is_history_enabled", lambda: True)
    monkeypatch.setattr(api, "get_history_db", _FakeHistoryDB)
    monkeypatch.setattr(api, "get_local_scrobble_db", lambda: None)

    body = client.get("/api/history/status").get_json()
    assert body["total_tracks"] == 5
    assert body["local_lastfm_enabled"] is False
    assert "library_tracks" not in body
    assert "library_plays" not in body
    assert "library_last_sync_at" not in body


def test_history_status_disabled_returns_enabled_false(client, monkeypatch):
    """History DB off (e.g. only Last.fm, or neither): status short-circuits."""
    from web.routes import api

    monkeypatch.setattr(api, "is_history_enabled", lambda: False)
    body = client.get("/api/history/status").get_json()
    assert body == {"enabled": False}


def test_history_top_tracks_uses_history_when_local_disabled(client, monkeypatch):
    """Only History DB enabled: top-tracks come from the resolution log."""
    from web.routes import api

    class _FakeHistoryDB:
        def get_top_tracks(self, _limit):
            return [{"artist": "A", "title": "X", "video_id": "v", "times_found": 3}]

    monkeypatch.setattr(api, "get_history_db", _FakeHistoryDB)
    monkeypatch.setattr(api, "get_local_scrobble_db", lambda: None)

    body = client.get("/api/history/top-tracks").get_json()
    assert body["source"] == "history"
    assert body["tracks"][0]["title"] == "X"


def test_history_top_tracks_requires_history_db(client, monkeypatch):
    """History DB off: top-tracks is unavailable even if Last.fm data exists."""
    from web.routes import api

    monkeypatch.setattr(api, "get_history_db", lambda: None)
    resp = client.get("/api/history/top-tracks")
    assert resp.status_code == 400


def test_history_near_misses_returns_ranked_rows(client, monkeypatch):
    """Near-misses endpoint returns rows with the cutoff from the first row."""
    from web.routes import api

    class _FakeHistoryDB:
        def get_near_misses(self, limit, offset):
            assert (limit, offset) == (50, 0)
            return [
                {"artist": "A", "title": "Close", "video_id": "v1", "score": 0.42, "plays": 3, "rank": 101, "cutoff": 100},
            ]

        def get_near_miss_count(self):
            return 1

    monkeypatch.setattr(api, "get_history_db", _FakeHistoryDB)
    body = client.get("/api/history/near-misses").get_json()
    assert body["total"] == 1
    assert body["cutoff"] == 100
    assert body["near_misses"][0]["title"] == "Close"


def test_history_near_misses_empty_cutoff_none(client, monkeypatch):
    """With no near-misses stored, cutoff is null."""
    from web.routes import api

    class _FakeHistoryDB:
        def get_near_misses(self, _limit, _offset):
            return []

        def get_near_miss_count(self):
            return 0

    monkeypatch.setattr(api, "get_history_db", _FakeHistoryDB)
    body = client.get("/api/history/near-misses").get_json()
    assert body["total"] == 0
    assert body["cutoff"] is None
    assert body["near_misses"] == []


def test_history_near_misses_requires_history_db(client, monkeypatch):
    """History DB off: near-misses endpoint returns 400."""
    from web.routes import api

    monkeypatch.setattr(api, "get_history_db", lambda: None)
    resp = client.get("/api/history/near-misses")
    assert resp.status_code == 400


def test_local_scrobble_db_singleton_reset_on_disable(monkeypatch, tmp_path):
    """Activate Last.fm DB then deactivate: reset clears the cached singleton."""
    pytest.importorskip("flask")

    import types

    from web.services import data

    db_file = tmp_path / "lfm.db"
    enabled = types.SimpleNamespace(use_local_lastfm_db=True, lastfm_local_db_file=str(db_file))
    monkeypatch.setattr(data, "_local_scrobble_db", None)
    monkeypatch.setattr(data.Settings, "from_env", staticmethod(lambda: enabled))

    first = data.get_local_scrobble_db()
    assert first is not None
    assert data.get_local_scrobble_db() is first  # cached singleton

    data.reset_local_scrobble_db()
    disabled = types.SimpleNamespace(use_local_lastfm_db=False, lastfm_local_db_file=str(db_file))
    monkeypatch.setattr(data.Settings, "from_env", staticmethod(lambda: disabled))
    assert data.get_local_scrobble_db() is None


def test_history_db_singleton_reset_on_disable(monkeypatch, tmp_path):
    """Activate History DB then deactivate: reset clears the cached singleton."""
    pytest.importorskip("flask")

    import types

    from web.services import data

    db_file = tmp_path / "hist.db"
    enabled = types.SimpleNamespace(history_db_enabled=True, history_db_file=str(db_file))
    monkeypatch.setattr(data, "_history_db", None)
    monkeypatch.setattr(data.Settings, "from_env", staticmethod(lambda: enabled))

    first = data.get_history_db()
    assert first is not None
    assert data.get_history_db() is first  # cached singleton

    data.reset_history_db()
    disabled = types.SimpleNamespace(history_db_enabled=False, history_db_file=str(db_file))
    monkeypatch.setattr(data.Settings, "from_env", staticmethod(lambda: disabled))
    assert data.get_history_db() is None


def test_history_top_tracks_delegates_to_local(client, monkeypatch, tmp_path):
    import time

    from src.lastfm import LocalScrobbleDB, Scrobble
    from web.routes import api

    now = int(time.time())
    local = LocalScrobbleDB(tmp_path / "lfm.db")
    local.ingest_scrobbles([Scrobble("A", "Hit", "", now), Scrobble("A", "Hit", "", now), Scrobble("B", "Deep", "", now)])

    monkeypatch.setattr(api, "get_history_db", object)
    monkeypatch.setattr(api, "get_local_scrobble_db", lambda: local)

    resp = client.get("/api/history/top-tracks?limit=10")
    body = resp.get_json()
    assert body["source"] == "local_lastfm"
    assert body["tracks"][0]["title"] == "Hit"
    assert body["tracks"][0]["plays"] == 2
    assert body["tracks"][0]["times_found"] == 2
    assert body["tracks"][0]["video_id"] is None


def test_setup_status_endpoint(client):
    resp = client.get("/api/setup/status")
    body = resp.get_json()
    assert body["needs_setup"] is True
    assert body["has_env"] is False


def test_scheduler_status_endpoint(client):
    resp = client.get("/api/scheduler/status")
    body = resp.get_json()
    assert "enabled" in body
    assert "available" in body


def test_cache_summary_endpoint(client):
    resp = client.get("/api/cache/summary")
    body = resp.get_json()
    assert set(body) == {"search", "tags", "playlists"}


def test_tag_overrides_and_suggestions_endpoints(client, web_paths):
    tc = TagCache(str(web_paths["TAG_CACHE_FILE"]))
    tc.set("A", "1", [{"name": "rock", "count": 50}])

    resp = client.get("/api/tag-overrides")
    assert resp.get_json() == {"overrides": []}

    resp = client.get("/api/tags/suggestions")
    assert "rock" in resp.get_json()["tags"]


def test_custom_playlists_get_empty(client):
    resp = client.get("/api/custom-playlists")
    assert resp.get_json() == {"playlists": []}


def test_failure_log_get_and_delete(client, web_paths):
    resp = client.get("/api/failure_log")
    assert resp.get_json() == {"has_failure": False}

    web_paths["FAILURE_LOG_FILE"].write_text(json.dumps({"error": "boom"}))
    resp = client.get("/api/failure_log")
    body = resp.get_json()
    assert body["has_failure"] is True
    assert body["error"] == "boom"

    resp = client.delete("/api/failure_log")
    assert resp.get_json() == {"status": "cleared"}
    resp = client.delete("/api/failure_log")
    assert resp.get_json() == {"status": "no_log"}


def test_panel_unknown_returns_404(client):
    resp = client.get("/api/panel/does-not-exist")
    assert resp.status_code == 404


def test_settings_post_no_data_returns_400(client):
    resp = client.post("/api/settings", json={})
    assert resp.status_code == 400


def test_settings_post_valid_writes_env(client, web_paths):
    resp = client.post("/api/settings", json={"PLAYLIST_NAME": "My List"})
    assert resp.status_code == 200
    assert "PLAYLIST_NAME" in resp.get_json()["updated"]
    assert "PLAYLIST_NAME=My List" in web_paths["ENV_FILE"].read_text()


def test_settings_post_invalid_cron_returns_400(client):
    resp = client.post(
        "/api/settings",
        json={
            "AUTO_SYNC_ENABLED": True,
            "AUTO_SYNC_TYPE": "cron",
            "AUTO_SYNC_CRON": "not a cron expr",
        },
    )
    assert resp.status_code == 400
    assert "error" in resp.get_json()


def test_settings_post_invalid_start_time_returns_400(client):
    resp = client.post("/api/settings", json={"AUTO_SYNC_START_TIME": "99:99"})
    assert resp.status_code == 400


def test_custom_playlists_post_requires_playlists_key(client):
    resp = client.post("/api/custom-playlists", json={})
    assert resp.status_code == 400


def test_custom_playlists_post_rejects_non_list(client):
    resp = client.post("/api/custom-playlists", json={"playlists": "nope"})
    assert resp.status_code == 400


def test_custom_playlists_post_cleans_and_saves(client, web_paths):
    payload = {
        "playlists": [
            {"name": "Chill", "tags": ["Ambient", " Chill "], "match": "bogus", "limit": -3},
            {"name": "", "tags": ["x"]},
            {"name": "NoTags", "tags": []},
        ]
    }
    resp = client.post("/api/custom-playlists", json=payload)
    assert resp.status_code == 200
    assert resp.get_json()["count"] == 1

    saved = json.loads(web_paths["CUSTOM_PLAYLISTS_FILE"].read_text())["playlists"]
    assert len(saved) == 1
    cleaned = saved[0]
    assert cleaned["tags"] == ["ambient", "chill"]
    assert cleaned["match"] == "any"
    assert cleaned["limit"] == 50


def test_cache_clear_search_all(client, web_paths):
    sc = SearchCache(str(web_paths["SEARCH_CACHE_FILE"]))
    sc.set("A", "1", "vidAAAAAAAA")
    sc.set("B", "2", "vidBBBBBBBB")

    resp = client.delete("/api/cache/search/all")
    assert resp.get_json() == {"deleted": 2}


def test_cache_clear_search_notfound(client, web_paths):
    sc = SearchCache(str(web_paths["SEARCH_CACHE_FILE"]))
    sc.set("A", "1", "vidAAAAAAAA")
    sc.set("B", "2", None)

    resp = client.delete("/api/cache/search/notfound")
    assert resp.get_json() == {"deleted": 1}


def test_cache_bulk_delete_search_validates_keys(client):
    resp = client.delete("/api/cache/search/bulk", json={"keys": "notalist"})
    assert resp.status_code == 400


def test_cache_bulk_delete_search(client, web_paths):
    sc = SearchCache(str(web_paths["SEARCH_CACHE_FILE"]))
    sc.set("A", "1", "vidAAAAAAAA")
    sc.set("B", "2", "vidBBBBBBBB")

    resp = client.delete("/api/cache/search/bulk", json={"keys": ["a|1"]})
    assert resp.get_json() == {"deleted": 1}


def test_cache_bulk_delete_tags_validates_keys(client):
    resp = client.delete("/api/cache/tags/bulk", json={"keys": "notalist"})
    assert resp.status_code == 400


def test_cache_clear_playlist_entry_not_found(client):
    resp = client.delete("/api/cache/playlist/entry", json={"name": "ghost"})
    assert resp.status_code == 404


def test_cache_clear_playlist_entry_requires_name(client):
    resp = client.delete("/api/cache/playlist/entry", json={})
    assert resp.status_code == 400


def test_cache_clear_playlist_track_requires_fields(client):
    resp = client.delete("/api/cache/playlist/track", json={"name": "x"})
    assert resp.status_code == 400


def test_cache_playlist_tracks_requires_name(client):
    resp = client.get("/api/cache/playlist-tracks")
    assert resp.status_code == 400


def test_action_blacklist_redirects_and_persists(client, web_paths):
    resp = client.post("/blacklist", data={"artist": "A", "title": "1", "reason": "bad"})
    assert resp.status_code == 302

    ov = SearchOverrides(str(web_paths["OVERRIDES_FILE"]))
    assert ov.is_blacklisted("A", "1")


def test_action_override_invalid_video_id_returns_400(client):
    resp = client.post("/override", data={"artist": "A", "title": "1", "video_id": "short"})
    assert resp.status_code == 400


def test_action_override_missing_artist_returns_400(client):
    resp = client.post("/override", data={"artist": "", "title": "", "video_id": "dQw4w9WgXcQ"})
    assert resp.status_code == 400


def test_action_override_success_redirects_and_persists(client, web_paths):
    resp = client.post(
        "/override",
        data={"artist": "A", "title": "1", "video_id": "dQw4w9WgXcQ", "reason": "fix"},
    )
    assert resp.status_code == 302

    ov = SearchOverrides(str(web_paths["OVERRIDES_FILE"]))
    assert ov.get("A", "1") == "dQw4w9WgXcQ"


def test_action_override_extracts_id_from_url(client, web_paths):
    resp = client.post(
        "/override",
        data={"artist": "A", "title": "1", "video_id": "https://music.youtube.com/watch?v=dQw4w9WgXcQ"},
    )
    assert resp.status_code == 302
    ov = SearchOverrides(str(web_paths["OVERRIDES_FILE"]))
    assert ov.get("A", "1") == "dQw4w9WgXcQ"


def test_action_tag_override_requires_tags(client):
    resp = client.post("/tag_override", data={"artist": "A", "title": "1", "tags": ""})
    assert resp.status_code == 400


def test_action_tag_override_success(client):
    resp = client.post(
        "/tag_override",
        data={"artist": "A", "title": "1", "tags": "Rock, Metal", "mode": "replace"},
    )
    assert resp.status_code == 302


def test_export_import_round_trip(client, web_paths):
    ov = SearchOverrides(str(web_paths["OVERRIDES_FILE"]))
    ov.set("A", "1", "dQw4w9WgXcQ", reason="r")
    ov.blacklist("B", "2", reason="bl")

    resp = client.get("/export?type=all")
    exported = resp.get_json()
    assert "overrides" in exported
    assert "blacklist" in exported
    assert exported["_export_meta"]["type"] == "all"

    web_paths["OVERRIDES_FILE"].unlink()
    resp = client.post("/import", json=exported)
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["imported_overrides"] == 1
    assert body["imported_blacklist"] == 1


def test_import_no_data_returns_400(client):
    resp = client.post("/import", json={})
    assert resp.status_code == 400
