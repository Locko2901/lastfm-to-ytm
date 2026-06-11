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


def test_overrides_endpoint(client, web_paths):
    ov = SearchOverrides(str(web_paths["OVERRIDES_FILE"]))
    ov.set("A", "1", "vidAAAAAAAA", reason="r")
    ov.blacklist("B", "2", reason="bl")

    resp = client.get("/api/overrides")
    body = resp.get_json()
    assert len(body["overrides"]) == 1
    assert len(body["blacklist"]) == 1


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
