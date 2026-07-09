"""Shared pytest fixtures.

Web fixtures import Flask lazily *inside* the fixture body (never at module
top level) so the default dependency-light unit run - which installs only
``.[dev]`` without the ``web`` extra - is unaffected. Tests that request a web
fixture call ``pytest.importorskip("flask")`` themselves, so they skip cleanly
when the web extra is absent.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def web_paths(monkeypatch, tmp_path):
    """Redirect every file the web data/notification layer touches into ``tmp_path``.

    Forces ``_get_settings()`` to return ``None`` so the data layer falls back
    to the (now patched) module-level path constants instead of reading the
    real ``.env``/``Settings``. This keeps each test hermetic: fresh empty
    caches, no shared global state, and no history DB.
    """
    pytest.importorskip("flask")

    from web.services import data, env, notifications

    paths = {
        "ENV_FILE": tmp_path / ".env",
        "BROWSER_JSON_FILE": tmp_path / "browser.json",
        "OVERRIDES_FILE": tmp_path / "search_overrides.json",
        "SEARCH_CACHE_FILE": tmp_path / ".search_cache.json",
        "PLAYLIST_CACHE_FILE": tmp_path / ".playlist_cache.json",
        "TAG_CACHE_FILE": tmp_path / ".tag_cache.json",
        "TAG_OVERRIDES_FILE": tmp_path / "tag_overrides.json",
        "RUN_LOG_FILE": tmp_path / ".last_run_log.json",
        "FAILURE_LOG_FILE": tmp_path / ".last_failure.json",
        "CUSTOM_PLAYLISTS_FILE": tmp_path / "custom_playlists.json",
        "DRY_RUN_PREVIEW_FILE": tmp_path / ".dry_run_preview.json",
    }
    for name, path in paths.items():
        monkeypatch.setattr(data, name, path)

    monkeypatch.setattr(env, "ENV_FILE", paths["ENV_FILE"])
    monkeypatch.setattr(notifications, "_STORE_FILE", tmp_path / ".notifications.json")

    monkeypatch.setattr(data, "_get_settings", lambda: None)
    monkeypatch.setattr(data, "_history_db", None)

    return paths


@pytest.fixture
def flask_app(web_paths, monkeypatch):
    """Return the shared Flask app with a stub secret key (never writes .env)."""
    pytest.importorskip("flask")
    monkeypatch.setenv("FLASK_SECRET_KEY", "test-secret-key")

    from web.app import app

    app.config.update(TESTING=True)
    return app


@pytest.fixture
def client(flask_app):
    """A Flask test client backed by the hermetic ``web_paths`` fixture."""
    return flask_app.test_client()
