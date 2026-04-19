# Docker Internals

## Multi-Stage Dockerfile (`devops/Dockerfile`)

### Builder Stage

Based on `python:3.11-slim`, this stage compiles everything:

1. **Python venv** - installs all dependencies (`gunicorn`, `flask`, `flask-babel`, `apscheduler`, `cryptography`, `argon2-cffi`) into `/opt/venv`
2. **Babel compilation** - `pybabel compile -d web/translations` compiles `.po` &rarr; `.mo` catalogs
3. **esbuild** - downloads architecture-aware binary (`linux-x64` or `linux-arm64`), bundles and minifies:
    - `web/static/js/app.js` &rarr; `web/static/dist/app.min.js` (ESM format)
    - `web/static/css/bundle.css` &rarr; `web/static/dist/bundle.min.css`

### Production Stage

Slim runtime image with only what's needed:

- Installs `gosu`, `passwd`, `curl` (for health checks)
- Creates non-root `lastfm` user/group
- Copies compiled venv, source, minified assets, and translations from builder
- Sets `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`
- Entrypoint: `docker-entrypoint.sh`
- Default CMD: `gunicorn --config gunicorn.conf.py web.app:app`
- Exposes port 2002

---

## Entrypoint (`devops/docker-entrypoint.sh`)

The entrypoint handles permission mapping and file initialization:

1. **UID/GID matching** - reads the owner UID/GID of the `/app/config` mount and remaps the `lastfm` user to match via `usermod`/`groupmod`. This prevents permission conflicts with host-mounted volumes.
2. **File fixup** - creates `config/search_overrides.json` with empty structure if missing, fixes `.env` if it is accidentally a directory, ensures correct ownership on `cache/` and `config/`
3. **Privilege drop** - all subsequent commands run as the `lastfm` user via `gosu`

---

## Gunicorn Configuration (`devops/gunicorn.conf.py`)

| Setting | Value | Notes |
|---|---|---|
| Workers | `1` | Always 1 - `sync_state` lives in process memory |
| Worker class | `gthread` | Threads provide concurrency |
| Threads | Auto-detected | 2 on low-resource hosts (&le;1 CPU or <1 GB RAM), otherwise `min(cpu, 4) + 2` (3-6) |
| Preload | Auto-detected | Disabled on low-resource hosts |
| Timeout | `120` | Configurable via `GUNICORN_TIMEOUT` |
| Max requests | `1000` (+50 jitter) | Automatic worker recycling to prevent memory leaks |

Configurable via environment variables: `GUNICORN_BIND` (default `0.0.0.0:2002`), `GUNICORN_THREADS`, `GUNICORN_TIMEOUT`, `GUNICORN_LOG_LEVEL`, `GUNICORN_PRELOAD`.

After forking, `post_fork()` initializes the APScheduler instance from env settings.

---

## Docker Compose (`devops/docker-compose.yml`)

| Feature | Configuration |
|---|---|
| Port | `${YTMT_PORT:-2002}:2002` (configurable via env) |
| Health check | `curl -f http://localhost:2002/` every 30s, 10s timeout, 3 retries, 10s start period |
| Memory | 512 MB limit, 128 MB reservation |
| Restart | `unless-stopped` |
| Timezone | Host `/etc/localtime` mounted read-only + `TZ` env fallback |

**Volume mounts:**

| Host path | Container path | Mode |
|---|---|---|
| `cache/` | `/app/cache` | read-write |
| `config/` | `/app/config` | read-write |
| `browser.json` | `/app/browser.json` | read-write |
| `.env` | `/app/.env` | read-write |
| `.env.example` | `/app/.env.example` | read-only |
| `/etc/localtime` | `/etc/localtime` | read-only |
