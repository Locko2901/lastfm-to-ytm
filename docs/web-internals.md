# Web Dashboard Internals

## Flask App Factory (`web/app.py`)

The dashboard is a Flask app with these initialization steps:

1. **Secret key** - `_ensure_secret_key()` reads `FLASK_SECRET_KEY` from env/`.env`; auto-generates via `secrets.token_hex(32)` and persists under an `# AUTO-GENERATED` block if missing
2. **Babel** - `flask-babel` for i18n; locales auto-discovered from `web/translations/*/LC_MESSAGES/messages.po`
3. **Locale selection** - priority: `ytm-locale` cookie &rarr; `Accept-Language` header &rarr; `"en"` default
4. **CSP nonce** - generated per-request via `@app.before_request` using `secrets.token_urlsafe(16)`
5. **Minified asset detection** - checks for `web/static/dist/app.min.js` + `bundle.min.css` at startup
6. **JS translations** - `inject_globals()` context processor exports the Babel catalog to templates as `js_translations` dict, and the defaults of the switches the browser reads (`DASHBOARD_SWITCH_DEFAULTS`) as `switch_defaults`, which `base.html` puts on `window.__switchDefaults__`
7. **Blueprints** - registers `api_bp`, `auth_bp`, `sync_bp`, `actions_bp`, `notifications_bp`, `events_bp`, `scrobbler_bp`

---

## Security

The dashboard applies security headers to every response (`add_security_headers()` in `web/app.py`):

- **Content-Security-Policy** with per-request nonce for inline scripts: `script-src 'self' 'nonce-...'`, restricted `connect-src`, `font-src`, `img-src` (`'self'` + `data:` + `blob:` for images)
- **X-Frame-Options**: `SAMEORIGIN` (prevents clickjacking)
- **X-Content-Type-Options**: `nosniff`

The CSP nonce is generated via `secrets.token_urlsafe(16)` on every request and injected into templates as `csp_nonce`.

---

## Asset Pipeline

The app auto-detects minified assets at startup: if both `web/static/dist/app.min.js` and `bundle.min.css` exist, `use_minified` is set in Jinja globals. The Docker build produces these via esbuild; development mode uses unminified sources.

A `/manifest.json` route serves a PWA manifest from `web/static/`, making the dashboard installable as a Progressive Web App.

---

## Image Proxy

`GET /api/image-proxy` proxies external album art to enable CORS for canvas color extraction in the browser. Domain-allowlisted (`lastfm.freetls.fastly.net`, `lastfm-img2.akamaized.net`, `i.scdn.co`) with an in-memory LRU cache (50 entries, 1-hour TTL, 24-hour browser cache).

---

## Health & Readiness

Two lightweight probes (`web/routes/api.py`) let Docker, uptime monitors, or orchestrators check the app without touching external APIs:

- **`GET /api/healthz`** - *liveness*. Always returns `200 {"status": "ok"}` if the Flask app is serving. Cheap and side-effect free, safe to poll frequently. This is what the Docker `healthcheck` and `run-docker.sh` startup wait poll.
- **`GET /api/readyz`** - *readiness*. Verifies local prerequisites and returns `200` when ready, `503` otherwise:

  ```json
  {
    "ready": true,
    "checks": {"browser_json": true, "cache_dir_writable": true}
  }
  ```

  It checks only local state (YTM `browser.json` present, cache dir writable).

Note that `/api/readyz` returns `503` until first-time setup completes (before `browser.json` exists).

---

## Sync Process

Sync runs are executed as subprocesses (`subprocess.Popen`) from `web/routes/sync.py`:

- Only `run.py` and `run_tags.py` are allowed (hardcoded allowlist)
- Output is streamed to the browser via **Server-Sent Events** (`GET /sync_output`, `text/event-stream`)
- A **2-hour hard timeout** terminates stuck syncs (SIGTERM, then SIGKILL after 10s)
- The subprocess receives `SYNC_TRIGGER` (`"web"` or `"scheduled"`) and `HISTORY_SYNC_ID` env vars for audit trail
- Webhook settings are stripped from the subprocess env so it re-reads `.env` fresh (allows mid-session config changes)

### SSE Streaming

`stream_state_output()` yields Server-Sent Events:

- Output buffered in a `deque` (max 5000 lines)
- Polls every ~100ms for new output lines
- Event format: `data: {"line": "..."}` or `data: {"finished": true, "exit_code": N}`
- Error detection: greps last 20 lines for `error`, `exception`, `traceback` keywords

### Sync State

A global `sync_state` dict tracks the current run:

- `running`: bool flag (mutex via `sync_lock`)
- `started_at` / `finished_at`: timestamps
- `process`: subprocess handle for termination
- `output`: deque buffer

---

## Setup & Auth Endpoints

**Setup** (`web/routes/auth.py` or `web/routes/api.py`):

- `POST /api/setup/init` - copies `.env.example` &rarr; `.env`
- `POST /api/setup/lastfm` - saves Last.fm API key and username to `.env`
- `GET /api/setup/status` - checks whether `.env` exists, has required keys, and `browser.json` is valid

**Auth** (`web/routes/auth.py`):

- `POST /api/auth/submit` - parses raw browser request headers into `browser.json` format, tries them with one live YTM API call, and only when that works writes `browser.json` and publishes `auth_status` `{"valid": true}`; a signed-out answer (`is_signed_out`) or an unreachable YouTube Music returns the reason and leaves `browser.json` as it was
- `GET /api/auth/status` - validates `browser.json` exists and contains required cookies (`SAPISID` or `SID`)
- `GET /api/auth/test` - the same live call against the saved `browser.json`; a signed-out session answers `expired: true`

---

## Scheduler (`web/services/scheduler.py`)

APScheduler runs automated syncs in the background:

| Setting | Default | Description |
|---|---|---|
| `schedule_type` | `interval` | `"interval"` or `"cron"` |
| `interval_hours` | `6` | Hours between runs (interval mode) |
| `start_time` | `""` | HH:MM start for interval alignment |
| `cron_expression` | `0 */6 * * *` | Cron schedule |
| `tag_sync_enabled` | `false` | Run tag playlists alongside main sync |

**Job configuration**: `coalesce=True` (collapse missed runs into one), `max_instances=1` (no parallel syncs), `misfire_grace_time=3600` (accept up to 1 hour late).

### History scrobbler job

When `SCROBBLER_ENABLED` is on, `configure_scrobbler_job()` adds a second job,
`history_scrobbler`, that runs `web.services.scrobbler.run_scheduled_poll` every
`SCROBBLER_POLL_MINUTES` (first run 30 s after start-up). Each run is a tick:
`poll_if_due()` reads the pacing state from the store (last poll, last change of
the history, failed reads in a row) and only polls when
`src.scrobbler.pacing.poll_due()` says so for the fastest and idle intervals (see
[adaptive polling](scrobbler.md#adaptive-polling)); **Poll now** bypasses it.
`/api/scrobbler/status` reports the pace and the first tick at which a poll is
due as `next_poll`. It is independent of
`auto_sync`: it starts the scheduler on its own and is rescheduled live whenever
the settings save changes a `SCROBBLER_*` key. Polls run in-process (no
subprocess, they take a few seconds) behind a lock shared with
`POST /api/scrobbler/poll`, so a manual poll and a scheduled one never overlap.
The endpoints live in `web/routes/scrobbler.py` under `/api/scrobbler/`:
`status`, `plays`, `polls`, `poll`, `reset`, `dry-run-plays` (count, and the answer
to the offer made when the dry run is turned off), and `auth/start`, `auth/finish`,
`auth/disconnect` for the Last.fm connection. See
[History Scrobbler](scrobbler.md).

The scrobbler routes, this job and the history and local scrobble databases get
their `Settings` from `web.services.data.load_settings()`: read once per request
and cached on Flask `g`, read from `.env` again outside a request (the
scheduler) or with `fresh=True` right after a write (`auth/start` saves the API
secret first). The two jobs report their next run through the same
`_job_next_run()`.

A poll that finds the YouTube Music session expired (HTTP 401, or the signed-out
page that `src.ytm.is_signed_out` recognises, the same check `/api/auth/submit`
and `/api/auth/test` use) publishes `auth_status` with `{"valid": false,
"expired": true}`; `setup.js` then shows the auth banner in its expired variant.
The `/api/events` snapshot repeats that event for pages opened later, as long as
the last poll said so and `browser.json` is older than that poll. A valid
`auth_status` (a successful `/api/auth/submit`, or a poll that reads the history
again) removes the banner.

### Tag Sync Frequency Counter

When tag sync is enabled, a file counter (`runtime/.tag_sync_counter.json`) tracks how many main syncs have occurred since the last tag sync. Tag sync runs every **N** main syncs, where N is `AUTO_TAG_SYNC_FREQUENCY` (default `1` = every sync; `3` = every third scheduled main sync, etc.). The counter increments after each main sync and resets to `0` once it reaches N and the tag sync runs.

### Scheduled Sync Flow

1. Acquire `sync_lock` (skip if already running)
2. Run main sync via `_run_sync_process("run.py", trigger="scheduled")`
3. If tag sync is due: run `_run_sync_process("run_tags.py", trigger="scheduled")`
4. Record history DB sync entry with metrics
5. Update `scheduler_state` (last_run, success, next_run)

---

## Panel Endpoints

`GET /api/panel/<panel_name>` returns pre-rendered HTML fragments for partial page updates. Supported panels: `playlist`, `blacklist`, `overrides`, `cache`, `notfound`, `tags`, `custompl`, `history`.

---

## Theme overrides

CSS variable overrides edited from **Settings &rarr; Display &rarr; Customize colors** are persisted to `cache/.theme_overrides.json` (same folder as the search/playlist/tag caches) via `POST /api/theme`. Overrides are split per base theme (Dark / Light) and injected server-side into every page render, so the first paint already reflects the user's scheme (no flash of default theme). The file is included in the Teleporter cache picker for backup/restore.

---

## IPv4 Forcing (Dual Implementation)

IPv4-only mode uses two separate mechanisms:

- **Sync engine** (`src/lastfm/fetch.py`): monkey-patches `socket.getaddrinfo` globally to force `AF_INET`
- **Web dashboard** (`web/services/http.py`): `ipv4_session()` returns a shared `requests.Session` with a thread-safe `IPv4Adapter` (custom `HTTPAdapter` subclass) mounted, used by the now-playing and image-proxy endpoints and by the history scrobbler's Last.fm client
