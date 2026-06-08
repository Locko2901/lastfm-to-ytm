# Data & Security Model

This page describes **where every piece of credential, cache, and history data lives**,
how it is protected (or not), and what self-hosted operators should consider before
exposing the app outside a trusted network.

!!! warning "Trust model in one sentence"
    This app is designed to run on a **single-user, trusted host or LAN**. The web
    dashboard has **no built-in authentication**, and credentials are stored
    **plaintext on disk**. Put it behind a reverse proxy with auth (or keep it on
    localhost) before exposing it to the internet.

---

## At a glance

| Asset | Location | Encryption at rest | In git? |
|---|---|---|---|
| YouTube Music auth headers | [`browser.json`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/browser.json) | None | No |
| Last.fm API key + username | `.env` | None | No |
| Flask session secret | `.env` (`FLASK_SECRET_KEY`) | None | No |
| Webhook URL | `.env` (`WEBHOOK_URL`) | None | No |
| Search / playlist / tag caches | `cache/*.json` | None | No |
| History database (opt-in) | `cache/history.db` (SQLite, WAL) | None | No |
| User overrides & custom playlists | `config/*.json` | None | No (`.example` only) |
| Encrypted backup bundles | User-chosen `.bin` file | **AES-256-GCM + Argon2id** | No |

---

## 1. YouTube Music authentication

**File:** [`browser.json`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/browser.json) (configurable via `YTM_AUTH_PATH`,
see [`src/config.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/src/config.py))

`ytmusicapi` browser auth is used, which means the file contains a JSON object of
**raw browser request headers**: `Authorization`, `SAPISIDHASH`, the `__Secure-*`
cookies, `Cookie`, `User-Agent`, `x-goog-*` identifiers, etc.

- **Loaded by:** [`src/ytm/client.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/src/ytm/client.py) via the upstream
  `YTMusic()` constructor; orchestrated in
  [`src/workflows/_common.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/src/workflows/_common.py).
- **Submission UI:** the dashboard's "Setup" flow accepts pasted browser headers
  and writes them to disk ([`web/routes/auth.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/web/routes/auth.py)). The route is
  **not authenticated**.
- **Encryption:** none. Anyone with read access to the file can act as your
  Google account against YouTube Music until the cookies expire.
- **Rotation:** manual. Cookies expire periodically; re-paste headers when the
  dashboard reports auth errors.
- **Permissions (Docker):** the entrypoint normalises ownership to the `lastfm`
  user and `664` mode ([`devops/docker-entrypoint.sh`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/devops/docker-entrypoint.sh)).
  On the host you should keep the file `600` if running outside the container.
- **Git:** excluded via `.gitignore`.

## 2. Last.fm credentials

Stored as environment variables in `.env`:

- `LASTFM_USER` - username (not sensitive).
- `LASTFM_API_KEY` - API key. The dataclass field is marked `repr=False` in
  [`src/config.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/src/config.py) so it is **excluded from log output and
  tracebacks**.

There is no Last.fm session key - the app only reads public scrobbles, so
write-scope auth is never requested. The setup wizard can write these values via
the unauthenticated `/api/setup/lastfm` endpoint
([`web/routes/api.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/web/routes/api.py)).

## 3. Cache directory

All runtime state lives under `cache/` (overridable via `CACHE_DIR`). Every cache
file is plain JSON written through `JSONCache` in
[`src/cache/__init__.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/src/cache/__init__.py), which uses:

- atomic writes (temp file + `os.replace`), and
- `fcntl.flock()` for cross-process safety.

| File | Holds | Sensitivity |
|---|---|---|
| `.search_cache.json` | `artist\|title` &rarr; `video_id`, `yt_title`, timestamp (30-day TTL; 7 days for negative hits) | Medium |
| `.playlist_cache.json` | Playlist IDs and last-synced video-ID templates | Medium (playlist IDs) |
| `.tag_cache.json` | Last.fm tag lookups (90-day TTL) | Low |
| `.theme_overrides.json` | Dashboard theme tweaks | None |
| `.last_run_log.json` | Last sync's resolution map (powers the UI table) | Medium |
| `.tag_sync_counter.json` | Tag-sync cadence counter | None |
| `.update_check.json` | GitHub release version cache | None |
| `.notifications.json` | Web notification queue | None |
| `history.db` (+ `-shm`, `-wal`) | Opt-in audit DB (see below) | High |

None of these are encrypted. None contain Last.fm or Google credentials.

## 4. History database (optional)

**Disabled by default.** Enable with `HISTORY_DB_ENABLED=true`
([`src/config.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/src/config.py)). Path: `HISTORY_DB_FILE` (default
`cache/history.db`).

SQLite with WAL mode, foreign keys, thread-local connections - implemented in
[`src/history/db.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/src/history/db.py). Schema (v3):

- **`tracks`** - every resolved/missed `artist|title`, the chosen `video_id`,
  resolution `source` (search / cache / override / not_found / *_backfill),
  `first_seen`, `last_seen`, hit/miss counters, best match score.
- **`syncs`** - one row per sync run: timestamps, duration, type (`main`/`tags`),
  trigger (`manual`/`web`/`scheduled`), status, track counts, API and cache
  metrics, truncated error message.
- **`actions`** - audit log of user/system events: blacklist edits, override
  edits, cache clears, sync errors, substitutions, custom-playlist and tag
  events, backfills. Source is `web` or `cli`.

This DB is the most PII-rich artefact in the project: it's a full listening and
operator-action log. Treat it like a personal journal.

**Retention and vacuum.** Two opt-in knobs keep the file from growing without
bound, both enforced after every successful main sync (and also exposed via the
**Vacuum &amp; Prune** button in **Settings &rarr; History Database**):

- `HISTORY_RETENTION_DAYS` (default `0` = disabled) - deletes any `syncs` and
  `actions` rows older than the cutoff, then runs `VACUUM` to release the
  freed pages back to the filesystem. `tracks` rows are deliberately preserved
  because they are cumulative lookup state, not audit history.
- `HISTORY_MAX_SIZE_MB` (default `0` = unlimited) - if the file is larger than
  the limit, deletes the oldest 100 `actions` and 50 `syncs` per pass until the
  file fits, then `VACUUM`s. `tracks` are also preserved here.

There is no automatic encryption of the file on disk - rely on filesystem-level
controls (LUKS, APFS FileVault, host permissions) if confidentiality matters.

**Export / import.** The full database can be dumped as JSON via
`GET /api/history/export` (or **Settings &rarr; Data Management &rarr; History
Database &rarr; Export**), and re-imported via `POST /api/history/import`
(multipart upload with a `mode=merge|replace` field, exposed in the UI as the
**Import** button + a confirmation modal). Both endpoints require
`HISTORY_DB_ENABLED=true` on the target instance. **Merge** is idempotent
(syncs deduped on `(started_at, sync_type)`, actions on the full content
tuple, tracks upserted on `(artist, title)`), so re-importing the same dump
is safe. **Replace** wipes the existing DB first. The exported JSON file is
**plaintext** - treat it with the same care as the raw DB. To carry it
encrypted, include the **History database** option inside a
[Teleporter](teleporter.md) bundle instead, which wraps the same JSON dump in
AES-256-GCM.

## 5. Encrypted backup / restore (Teleporter)

The only place the app encrypts anything at rest. See
[Teleporter docs](teleporter.md) and
[`web/services/teleporter.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/web/services/teleporter.py).

- **Cipher:** AES-256-GCM (AEAD).
- **KDF:** Argon2id - 128 MiB memory, 3 iterations, 4 threads.
- **Nonce:** 12 random bytes per export; **salt:** 16 random bytes.
- **Format:** `TPRT` magic header + version + metadata + ciphertext.
- **Password policy:** minimum 8 characters, enforced server-side.
- **Dependencies:** `cryptography>=41`, `argon2-cffi>=23.1`.

A bundle can include `.env`, `browser.json`, all `config/*.json` overrides, and
(optionally) any chosen cache files. **The bundle contains your Last.fm API
key and YouTube cookies** - store the `.bin` file and its password as you would
any password vault export.

## 6. Web dashboard security

- **No login.** There is no user table, no password, no API token. Every route
  under `/api/*`, `/auth/*`, `/sync/*`, and `/actions/*` is reachable by anyone
  who can hit the port.
- **No CSRF protection.** Flask-WTF is not installed; state-changing endpoints
  accept any same-origin (or cross-origin, depending on browser) POST.
- **Flask session secret** (`FLASK_SECRET_KEY`): generated once via
  `secrets.token_hex(32)` and appended to `.env` under an `AUTO-GENERATED`
  section by [`web/app.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/web/app.py). It persists across restarts; deleting it
  invalidates any open sessions.
- **Cookies:** Flask defaults (HTTPOnly). Mark them `Secure` by terminating TLS
  at a reverse proxy.

**Recommended deployment:** bind to `127.0.0.1` (or a private Docker network)
and front it with nginx/Caddy/Traefik doing TLS + Basic Auth, OAuth2 Proxy,
Authelia, Tailscale ACLs, or similar.

## 7. Docker

[`devops/docker-compose.yml`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/devops/docker-compose.yml) mounts host paths
read-write so the container can persist state back to the host:

```yaml
volumes:
  - ../cache:/app/cache
  - ../config:/app/config
  - ../browser.json:/app/browser.json
  - ../.env:/app/.env
  - ../.env.example:/app/.env.example:ro
  - /etc/localtime:/etc/localtime:ro
```

- The container runs as a non-root `lastfm` user; the entrypoint matches its
  UID/GID to the owner of `/app/config` so host-side files keep sensible
  permissions ([`devops/docker-entrypoint.sh`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/devops/docker-entrypoint.sh)).
- **No Docker secrets are used.** Credentials are bind-mounted from the host
  `.env` / `browser.json`. If you prefer Docker/Swarm/K8s secrets, mount them at
  the same in-container paths.
- Avoid putting `LASTFM_API_KEY` in `environment:` in compose - it ends up in
  `docker inspect` output. Stick with the `.env` mount.

## 8. Webhooks

Configured via `WEBHOOK_URL` and `WEBHOOK_EVENTS` ([`src/webhook.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/src/webhook.py)).

- The outbound payload is **not signed**; the receiver has no way to verify it
  came from this app. If you need authenticity, embed a shared secret in the URL
  (Discord-style) and validate on the receiver.
- Payloads include sync status, track counts, API/cache metrics, the playlist
  URL, and truncated error messages - no credentials.
- Timeout 10s, no retries.

## 9. Configuration overrides

Files under `config/` (paths set by `CACHE_OVERRIDES_FILE`,
`TAG_OVERRIDES_FILE`, `CUSTOM_PLAYLISTS_FILE`):

| File | Purpose |
|---|---|
| `search_overrides.json` | Manual `artist\|title &rarr; video_id` fixes and a blacklist |
| `tag_overrides.json` | Forced Last.fm tag assignments |
| `custom_playlists.json` | Tag-based playlist definitions |

Tracked in git only as `*.example` templates. Plaintext JSON; not sensitive on
their own, but they reveal listening preferences.

## 10. Environment variables

The canonical list lives in `.env.example` and is documented on the
[Configuration](configuration.md) page. The only **sensitive** keys are:

- `LASTFM_API_KEY`
- `FLASK_SECRET_KEY` (auto-generated)
- `WEBHOOK_URL` (if it embeds a token)

Anything else controls behaviour, not access.

## 11. What's excluded from git

`.gitignore` keeps the following out of the repository:

- `.env`, `browser.json`, `.channel`
- `/cache/` (entire directory, including `history.db`)
- `config/*.json` with a `!config/*.example` (and `!config/*.json.example`)
  whitelist - any real override file you drop into `config/` is ignored by
  default; only the `.example` templates are committed
- `*.log`, `*.bak`
- `__pycache__/`, `.venv*/`, `dist/`, `build/`, `site/`, `*.egg-info/`,
  `node_modules/`, `.ruff_cache/`
