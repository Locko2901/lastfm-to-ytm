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
2. **File fixup** - creates `config/search_overrides.json` with empty structure if missing, fixes `.env` if it is accidentally a directory, ensures correct ownership on `runtime/` and `config/`
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
| `runtime/` | `/app/runtime` | read-write |
| `config/` | `/app/config` | read-write |
| `browser.json` | `/app/browser.json` | read-write |
| `.env` | `/app/.env` | read-write |
| `.env.example` | `/app/.env.example` | read-only |
| `/etc/localtime` | `/etc/localtime` | read-only |

The `image:` field in compose defaults to `lastfm-to-ytm-web:local` (the
locally built tag) but can be overridden via the `YTMT_IMAGE` environment
variable to use a prebuilt image instead - this is what
`./run-docker.sh --pull` does. By default `--pull` targets GHCR; pass
`--registry=dockerhub` (or set `YTMT_REGISTRY=dockerhub`) to pull the Docker Hub
mirror instead. Setting `YTMT_IMAGE` directly bypasses the registry selection.

---

## Published Images (GHCR + Docker Hub)

The `docker-publish` job in [`ci.yml`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/.github/workflows/ci.yml) builds and pushes multi-arch images to GitHub Container Registry. It runs after every linter job (`python`, `types`, `js-css`, `templates`, `templates-format`) passes, and `release-please` in turn depends on it - so a failed publish blocks the release tag.

- **Registry**: `ghcr.io/locko2901/lastfm-to-ytm` (primary), mirrored to `docker.io/lockooo/lastfm-to-ytm`
- **Architectures**: `linux/amd64`, `linux/arm64` (via QEMU + Buildx)
- **Triggers & tags**:
    - Push to `main` (untagged commits) &rarr; `:dev`, `:sha-<short>` - rolling development channel.
    - `v*.*.*` tag (created by release-please) &rarr; `:vX.Y.Z`, `:X.Y`, `:X`, `:latest` - stable release channel.
    - `:latest` is **only** published from release tags - it never points at an untagged `main` commit.
- **Caching**: GitHub Actions cache (`type=gha`) keeps incremental builds fast.
- **Auth**: `GITHUB_TOKEN` with `packages: write` for GHCR; no extra secret required.

The build re-uses the exact same `devops/Dockerfile` (production target)
that local builds use, so a prebuilt image is byte-equivalent to a clean
`./run-docker.sh --no-cache` build of the same commit.

### Docker Hub mirror

The Docker Hub push is **opt-in** and gated on the `DOCKERHUB_IMAGE` repository
variable. When it is empty the pipeline behaves exactly as before (GHCR only);
when it is set, the dev build pushes to both registries in a single build and
the release job mirrors the semver + `latest` tags with `docker buildx imagetools create`.
