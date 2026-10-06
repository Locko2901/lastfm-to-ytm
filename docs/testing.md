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
| Last.fm write client | `test_lastfm_client.py` | Request signing, token/session flow, `track.scrobble` array params and batches of 50, retries and backoff, error codes 9/14/29, recent tracks paging and now playing (fake transport) |
| History scrobbler | `test_scrobbler_detect.py`, `test_scrobbler_played.py`, `test_scrobbler_pacing.py`, `test_scrobbler_realtime.py`, `test_scrobbler_matching.py`, `test_scrobbler_dedup.py`, `test_scrobbler_service.py` | Snapshot diffing (new plays, replays, the same song twice, shelf moves, resets), confirmation by the next poll (a row moved up, a row missing, a stale list, baseline and reset), listening bounds, the threshold, certain and estimated decisions and the tie-break (checked against Monte Carlo), end unknown and timing unknown with their models, adaptive pacing, real-time activity periods (gap, idle polls, clock slack), artist/title matching, uploads and near misses, the duplicate window edges, history reads retried like the sync (rate limits and server errors retried, 400, 409 and an expired authentication not, the 401 and the recorded signed-out history page as an expired session, a notice shelf shown with its title, no error message shown as "None"), full polls against a fake history and fake Last.fm (dry run, live, restarts, Last.fm unreachable, unanswered batches, ledger, and plays left to a real-time scrobbler: a computer session with skips, a phone session after it, switching devices, an idle real-time scrobbler) |
| Played-rule simulation | `test_scrobbler_simulation.py` | A reduced run of `scripts/scrobbler_simulation.py` (confirmation keeps flickers from inventing plays, no false scrobbles without pauses, shorter intervals cost less, pacing, deferring to a real-time scrobbler), that every poll of a simulated session is a run of the real `Poller` on a temporary database, the fake real-time scrobbler of the computer, the decision log read back as outcomes, and parallel runs scoring like serial ones. The full run behind the tables in [History Scrobbler](scrobbler.md#what-the-poll-interval-changes) takes a few minutes: `python scripts/scrobbler_simulation.py --check` (or `--write` after changing the rule) |
| Scrobbler routes | `test_scrobbler_routes.py` | Status, decision log filters, poll now, reset, the dry-run offer (counts, sending only plays Last.fm still accepts, declining, asked once), the Connect Last.fm endpoints writing `.env` (and reporting a failed write), settings never returning the session key, poll interval validation, `auth_status` published for an expired YouTube Music session and kept in the events snapshot until `browser.json` is replaced |
| Config | `test_config.py` | Env parsers, `Settings.from_env()`, `load_custom_playlists` |
| Cache | `test_json_cache.py`, `test_search_cache.py`, `test_playlist_cache.py` | Atomic writes, TTL eviction, the `template_changed` sync gate |
| Playlist sync | `test_sync_helpers.py`, `test_ytm_retry.py` | Retry/backoff (shared with the history scrobbler's reads), video-ID validation, reorder, substitution detection |
| YouTube Music session | `test_ytm_session.py` | The shared signed-out check (`YTMusicServerError(None)`, "Sign in", a missing `singleColumnBrowseResultsRenderer`) and `/api/auth/test` reporting such a session as expired |
| History DB | `test_history_db.py`, `test_db.py` | Tracks/syncs/actions CRUD, stats, backfill, prune, export/import; the SQLite base shared by the stores (`src/db.py`: a connection per thread with WAL and rows, rollback of a failing block, the meta table) |
| Web backend (services) | `test_env_file.py`, `test_theme_overrides.py`, `test_update_check.py`, `test_web_data.py`, `test_notifications_store.py` | `.env` round-tripping, theme sanitising, version parsing, dashboard data-shaping (`web/services/data.py`), notification store (add/dedup/prune/delete/clear/mark-read) |
| Web backend (routes) | `test_web_routes.py` | Flask endpoints exercised through `test_client`: read APIs (`/api/stats`, `/api/cache-stats`, `/api/overrides`, `/api/settings`, `/api/scheduler/status`, `/api/cache/summary`, …), validation branches (settings cron/start-time, custom-playlist cleaning, cache-bulk key checks, `/api/panel/<unknown>` 404), and form actions (`/blacklist`, `/override`, `/tag_override`, `/export`+`/import`), plus the notification routes, every switch missing from `.env` reading as the default its reader uses, and the scrobbler interval inputs taking their limits from the dashboard context |

!!! note "Web-backend tests guard on Flask"
    Every `web/`-touching test file (`tests/test_env_file.py`, `tests/test_theme_overrides.py`, `tests/test_update_check.py`, `tests/test_web_data.py`, `tests/test_web_routes.py`, `tests/test_notifications_store.py`) starts with `pytest.importorskip("flask")`, because the CI unit job installs only `.[dev]` (no `web` extra). They skip cleanly there and run locally / in the `tests` job where the `web` extra is present - the same pattern the frontend suite uses for Playwright.

!!! tip "Shared web fixtures"
    [`tests/conftest.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/tests/conftest.py) provides `web_paths` (redirects every cache/config/`.env`/notification file into `tmp_path` and forces the settings fallback), `flask_app` (the dashboard app with a stub `FLASK_SECRET_KEY` so it never writes a real `.env`), and `client` (a `test_client`). Flask is imported lazily *inside* those fixtures, so the dependency-light unit run is unaffected.

### What the web tests deliberately skip

The route/service tests cover only the file-backed, offline-deterministic logic. The following are intentionally left to manual runs and the frontend e2e layer because mocking a live YouTube Music session, outbound HTTP, or a subprocess costs more than it's worth:

- `/api/now-playing`, `/api/image-proxy` - live Last.fm / image-CDN HTTP.
- `web/services/scrobbler.py`'s real poll glue - builds the YouTube Music client from `YTM_AUTH_PATH` like the sync and talks to Last.fm; the poll logic it wraps is covered by `test_scrobbler_service.py` with fakes.
- `/api/webhook/test` - outbound webhook POST.
- `/api/restart` - sends process signals / exits the worker.
- `/api/track-detail` and the history routes - only meaningful with a populated history DB (covered by `test_history_db.py`).
- `auth_bp` / `sync_bp` - require a YouTube Music session or spawn the sync subprocess.
- `/api/setup/init`, `/api/setup/lastfm` - copy/write real example files outside the patched paths; the underlying `env` helpers are unit-tested in `test_env_file.py`.
- `delete_custom_playlist_data(..., delete_from_ytm=True)` - instantiates `ytmusicapi.YTMusic`.
- The SSE stream endpoint (`events_bp`) - needs a long-lived streaming client; the broadcast call is exercised indirectly by the notification-store tests.

## Frontend e2e tests

[`tests/frontend/test_dashboard.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/tests/frontend/test_dashboard.py) drives the real dashboard with Playwright. It reuses the Flask fixture server and stubbed API routes from [`tests/screenshots/generate.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/tests/screenshots/generate.py), so the page renders with deterministic demo data and never touches real credentials or the live APIs. The whole module is skipped automatically when Playwright (or the `web`/`web-docs` extra) is missing, keeping the default unit run dependency-light.

These cover DOM wiring - tab switching, modal/drawer opening, and a no-uncaught-error smoke check on load - plus the shared helpers in `utils.js` and `tabs.js` (`fetchJson`, `setText`, `setPagination`, `setTabVisibility`) and the Scrobbler tab (loading on click, filters, a toast on a network error, the phone layout). There is no JavaScript unit-test framework; the pure JS logic that exists (date formatting, filter predicates) is small and is exercised through this e2e layer.

## Coverage

Coverage is configured in `pyproject.toml` under `[tool.coverage.run]` with `source = ["src", "web"]` and `branch = true`. Both the core (`src/`) and the web backend (`web/`) are measured, so the web-backend tests above move the reported number.

The deliberately-untested remainder is the API / network / orchestration glue ([`src/workflows/`](https://github.com/Locko2901/lastfm-to-ytm/tree/main/src/workflows), `src/lastfm/fetch.py`, `src/ytm/operations.py`, `src/search/executor.py`, `src/tags/sync.py`) plus the web layers that need a live session, outbound HTTP, or a subprocess ([`web/routes/auth.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/web/routes/auth.py), [`web/routes/sync.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/web/routes/sync.py), `web/services/scheduler.py`, `web/services/teleporter.py`, `web/services/update_check.py`'s network paths - see [What the web tests deliberately skip](#what-the-web-tests-deliberately-skip)). These are thin wrappers over external services where the mocking cost outweighs the value; they are verified manually via `python run.py` or the dashboard. The pure logic *inside* the resolver/observability layers (`src/search/resolver.py`, `src/tags/resolver.py`, `src/observability/failure_log.py`, `src/observability/history_recording.py`) and the dashboard data/route layers (`web/services/data.py`, `web/routes/api.py`, `web/routes/actions.py`, `web/services/notifications.py`) is unit-tested directly by stubbing or redirecting the I/O each performs.

## Writing tests

- Put pure-logic tests in `tests/test_<module>.py`. No docstrings or magic-number assertions are required there (`D` and `PLR2004` are ignored for `tests/test_*.py` in `pyproject.toml`).
- Use `tmp_path` for anything that touches the filesystem - never write into the repo's real `cache/` or `config/`.
- Keep tests offline. If a function calls YouTube Music or Last.fm, either test a pure helper it delegates to or pass a small fake client. The `no_network` fixture in `tests/conftest.py` fails a test on any HTTP request or socket connection; the scrobbler tests use it module-wide.
- If a test imports from `web/`, guard the module with `pytest.importorskip("flask")`. For route/service tests, reuse the `web_paths` / `flask_app` / `client` fixtures from `tests/conftest.py` instead of touching real files.
- Run `./precommit.sh` before pushing; it runs Ruff, both pytest layers, and the rest of the checks.
