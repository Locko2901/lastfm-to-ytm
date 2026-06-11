# Testing

The test suite lives under [`tests/`](https://github.com/Locko2901/lastfm-to-ytm/tree/main/tests) and is split into two layers:

| Layer | Location | Runner | Needs a browser? |
|---|---|---|---|
| **Unit** (pure logic + cache/DB I/O) | `tests/test_*.py` | `pytest` | No |
| **Frontend e2e** (dashboard) | `tests/frontend/` | `pytest` + [Playwright](https://playwright.dev/python/) | Yes (Chromium) |

Both run automatically in CI and via [`./precommit.sh`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/precommit.sh).

## Quick Reference

```bash
# Unit tests (fast, no browser, no network)
.venv/bin/python -m pytest --ignore=tests/frontend

# Unit tests with coverage (matches CI)
.venv/bin/python -m pytest --ignore=tests/frontend --cov --cov-report=term

# Frontend e2e (requires the web + web-docs extras + a browser)
pip install -e ".[dev,web,web-docs]"
python -m playwright install chromium
.venv/bin/python -m pytest tests/frontend
```

## Unit tests

Unit tests are pure and deterministic - no network, no real YouTube Music / Last.fm calls. File-backed components (caches, the history DB, the `.env` parser) are tested against pytest's `tmp_path` fixture, and the few helpers that take a `YTMusic` client use a small in-test fake. They run in a couple of seconds.

| Area | Test file | Covers |
|---|---|---|
| Search matching | `test_normalization.py`, `test_queries.py`, `test_scoring.py`, `test_similarity.py` | Text normalization, query building, candidate scoring, fuzzy similarity |
| Search resolution | `test_search_resolver.py` | Three-tier priority (override &rarr; cache &rarr; API), negative caching, blacklist skip, duplicate collapse (stubbed `find_on_ytm`) |
| Recency | `test_weighting.py` | Exponential-decay weighting and collapse |
| Tags | `test_tag_filter.py`, `test_tag_cache.py`, `test_tags_resolver.py` | Tag filtering, `TagCache` TTL, `TagOverrides` add/replace merge, cache-first tag resolution (stubbed `fetch_track_tags`) |
| Observability | `test_failure_log.py`, `test_history_recording.py` | Failure/run-log writes + hint mapping, miss classification into the history DB |
| Weekly | `test_weekly.py` | Weekly playlist naming and prefix derivation |
| HTTP status | `test_http_status.py` | Upstream error classification (retryable / rate-limit / terminal) |
| Config | `test_config.py` | Env parsers, `Settings.from_env()`, `load_custom_playlists` |
| Cache | `test_json_cache.py`, `test_search_cache.py`, `test_playlist_cache.py` | Atomic writes, TTL eviction, the `template_changed` sync gate |
| Playlist sync | `test_sync_helpers.py` | Retry/backoff, video-ID validation, reorder, substitution detection |
| History DB | `test_history_db.py` | Tracks/syncs/actions CRUD, stats, backfill, prune, export/import |
| Web backend (services) | `test_env_file.py`, `test_theme_overrides.py`, `test_update_check.py`, `test_web_data.py`, `test_notifications_store.py` | `.env` round-tripping, theme sanitising, version parsing, dashboard data-shaping (`web/services/data.py`), notification store (add/dedup/prune/delete/clear/mark-read) |
| Web backend (routes) | `test_web_routes.py` | Flask endpoints exercised through `test_client`: read APIs (`/api/stats`, `/api/cache-stats`, `/api/overrides`, `/api/settings`, `/api/scheduler/status`, `/api/cache/summary`, …), validation branches (settings cron/start-time, custom-playlist cleaning, cache-bulk key checks, `/api/panel/<unknown>` 404), and form actions (`/blacklist`, `/override`, `/tag_override`, `/export`+`/import`), plus the notification routes |

!!! note "Web-backend tests guard on Flask"
    Every `web/`-touching test file (`tests/test_env_file.py`, `tests/test_theme_overrides.py`, `tests/test_update_check.py`, `tests/test_web_data.py`, `tests/test_web_routes.py`, `tests/test_notifications_store.py`) starts with `pytest.importorskip("flask")`, because the CI unit job installs only `.[dev]` (no `web` extra). They skip cleanly there and run locally / in the `tests` job where the `web` extra is present - the same pattern the frontend suite uses for Playwright.

!!! tip "Shared web fixtures"
    [`tests/conftest.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/tests/conftest.py) provides `web_paths` (redirects every cache/config/`.env`/notification file into `tmp_path` and forces the settings fallback), `flask_app` (the dashboard app with a stub `FLASK_SECRET_KEY` so it never writes a real `.env`), and `client` (a `test_client`). Flask is imported lazily *inside* those fixtures, so the dependency-light unit run is unaffected.

### What the web tests deliberately skip

The route/service tests cover only the file-backed, offline-deterministic logic. The following are intentionally left to manual runs and the frontend e2e layer because mocking a live YouTube Music session, outbound HTTP, or a subprocess costs more than it's worth:

- `/api/now-playing`, `/api/image-proxy` - live Last.fm / image-CDN HTTP.
- `/api/webhook/test` - outbound webhook POST.
- `/api/restart` - sends process signals / exits the worker.
- `/api/track-detail` and the history routes - only meaningful with a populated history DB (covered by `test_history_db.py`).
- `auth_bp` / `sync_bp` - require a YouTube Music session or spawn the sync subprocess.
- `/api/setup/init`, `/api/setup/lastfm` - copy/write real example files outside the patched paths; the underlying `env` helpers are unit-tested in `test_env_file.py`.
- `delete_custom_playlist_data(..., delete_from_ytm=True)` - instantiates `ytmusicapi.YTMusic`.
- The SSE stream endpoint (`events_bp`) - needs a long-lived streaming client; the broadcast call is exercised indirectly by the notification-store tests.

## Frontend e2e tests

[`tests/frontend/test_dashboard.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/tests/frontend/test_dashboard.py) drives the real dashboard with Playwright. It reuses the Flask fixture server and stubbed API routes from [`tests/screenshots/generate.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/tests/screenshots/generate.py), so the page renders with deterministic demo data and never touches real credentials or the live APIs. The whole module is skipped automatically when Playwright (or the `web`/`web-docs` extra) is missing, keeping the default unit run dependency-light.

These cover DOM wiring - tab switching, modal/drawer opening, and a no-uncaught-error smoke check on load. There is no JavaScript unit-test framework; the pure JS logic that exists (date formatting, filter predicates) is small and is exercised through this e2e layer.

## Coverage

Coverage is configured in `pyproject.toml` under `[tool.coverage.run]` with `source = ["src", "web"]` and `branch = true`. Both the core (`src/`) and the web backend (`web/`) are measured, so the web-backend tests above move the reported number.

The deliberately-untested remainder is the API / network / orchestration glue ([`src/workflows/`](https://github.com/Locko2901/lastfm-to-ytm/tree/main/src/workflows), `src/lastfm/fetch.py`, `src/ytm/operations.py`, `src/search/executor.py`, `src/tags/sync.py`) plus the web layers that need a live session, outbound HTTP, or a subprocess ([`web/routes/auth.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/web/routes/auth.py), [`web/routes/sync.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/web/routes/sync.py), `web/services/scheduler.py`, `web/services/teleporter.py`, `web/services/update_check.py`'s network paths - see [What the web tests deliberately skip](#what-the-web-tests-deliberately-skip)). These are thin wrappers over external services where the mocking cost outweighs the value; they are verified manually via `python run.py` or the dashboard. The pure logic *inside* the resolver/observability layers (`src/search/resolver.py`, `src/tags/resolver.py`, `src/observability/failure_log.py`, `src/observability/history_recording.py`) and the dashboard data/route layers (`web/services/data.py`, `web/routes/api.py`, `web/routes/actions.py`, `web/services/notifications.py`) is unit-tested directly by stubbing or redirecting the I/O each performs.

## Writing tests

- Put pure-logic tests in `tests/test_<module>.py`. No docstrings or magic-number assertions are required there (`D` and `PLR2004` are ignored for `tests/test_*.py` in `pyproject.toml`).
- Use `tmp_path` for anything that touches the filesystem - never write into the repo's real `cache/` or `config/`.
- Keep tests offline. If a function calls YouTube Music or Last.fm, either test a pure helper it delegates to or pass a small fake client.
- If a test imports from `web/`, guard the module with `pytest.importorskip("flask")`. For route/service tests, reuse the `web_paths` / `flask_app` / `client` fixtures from `tests/conftest.py` instead of touching real files.
- Run `./precommit.sh` before pushing; it runs Ruff, both pytest layers, and the rest of the checks.
