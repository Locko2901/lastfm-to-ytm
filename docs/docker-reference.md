# Docker Reference

Detailed reference for `run-docker.sh`, the prebuilt image, updating, and release channels. If you just want to install, see the [Quickstart](quickstart.md) first.

## CLI options

```bash
./run-docker.sh [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--rebuild` | `-r` | Force rebuild the Docker image |
| `--no-cache` | | Rebuild without Docker cache (implies `--rebuild`) |
| `--pull` | `-p` | Use the prebuilt image from GHCR instead of building locally (`--pull=TAG` to pin a tag) |
| `--channel=CH` | | One-shot override of the auto-detected channel (`stable` or `dev`) for this run only. Normally not needed - channel is inferred from `--pull` / git state and written to `.channel` in the project root |
| `--stop` | | Stop the running container |
| `--logs` | `-l` | Follow container logs |
| `--status` | | Show container status |
| `--prune` | | Remove dangling images and old project images |
| `--prune-all` | | Aggressive cleanup: also clear build cache and unused images |
| `--help` | `-h` | Show help message |

Options can be combined, e.g. `./run-docker.sh --no-cache --prune` to do a fresh rebuild and cleanup.

### Common commands

```bash
./run-docker.sh              # Start (default)
./run-docker.sh --logs       # Follow container logs
./run-docker.sh --stop       # Stop the container
./run-docker.sh --status     # Check if running
./run-docker.sh --no-cache   # Force rebuild with fresh dependencies
./run-docker.sh --rebuild --prune  # Rebuild and clean up old images
```

The Docker setup:

- Runs a Flask web dashboard with Gunicorn behind the scenes
- Persists cache and config data in local directories
- Auto-restarts unless manually stopped

---

## Environment variables (host-side)

These are set on the host shell, not in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `YTMT_PORT` | `2002` | Port to expose the web dashboard |
| `YTMT_HEALTH_TIMEOUT` | `30` | Seconds to wait for health check |
| `YTMT_IMAGE` | `lastfm-to-ytm-web:local` | Full image reference compose uses (override to pin a prebuilt tag) |

---

## Building from source (clone the repo)

Use this if you want to build the image locally, contribute, or modify the source. **Stable requires explicitly checking out a release tag** - a plain `git clone` always lands on `main` and stays on the dev channel (see [Release Channels](channels.md)).

=== "Stable channel"

    ```bash
    git clone https://github.com/Locko2901/lastfm-to-ytm.git
    cd lastfm-to-ytm
    git checkout "$(git tag --sort=-v:refname | head -1)"   # latest release tag
    chmod +x run-docker.sh
    ./run-docker.sh    # builds locally; channel auto-detected as stable
    ```

=== "Dev channel"

    ```bash
    git clone https://github.com/Locko2901/lastfm-to-ytm.git
    cd lastfm-to-ytm
    chmod +x run-docker.sh
    ./run-docker.sh    # builds locally from main; channel auto-detected as dev
    ```

See available tags on the [releases page](https://github.com/Locko2901/lastfm-to-ytm/releases) or with `git tag --list 'v*' | sort -V`. To pin a specific release instead of the latest tag, replace the `git checkout` line with `git checkout v1.2.0`.

---

## Using the prebuilt image

Multi-arch images (`linux/amd64`, `linux/arm64`) are published to GitHub Container Registry on every push to `main` and on every tagged release. The same tags are mirrored to Docker Hub (`docker.io/lockooo/lastfm-to-ytm`).

```bash
./run-docker.sh --pull              # pulls ghcr.io/locko2901/lastfm-to-ytm:latest
./run-docker.sh --pull=v1.2.0       # pin a specific version
./run-docker.sh --pull=main         # always-fresh main branch build
```

Both registries carry identical images, so you can pull from whichever you prefer:

```bash
docker pull ghcr.io/locko2901/lastfm-to-ytm:latest    # GitHub Container Registry
docker pull lockooo/lastfm-to-ytm:latest              # Docker Hub mirror
```

Available tags:

| Tag | Tracks | Channel |
|---|---|---|
| `latest` | The most recent tagged release | stable |
| `vX.Y.Z`, `X.Y`, `X` | A specific release (semver) | stable |
| `dev` | Latest untagged commit on `main` | development |
| `sha-<short>` | A specific `main` commit | development |

!!! note
    `latest` only moves when a new release tag is published - it never points at an untagged `main` commit. Use `dev` if you want the bleeding edge.

You can also bypass the launcher entirely - pulling and running the image with plain `docker` works fine, as long as you mount `cache/`, `config/`, `.env`, and `browser.json` the same way [`devops/docker-compose.yml`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/devops/docker-compose.yml) does.

---

## Updating

The version pill in the dashboard header lights up when a newer build is available. What "newer" means depends on your channel:

- **stable** - a newer release tag has been published (e.g. `v1.0.2` when you're on `v1.0.1`).
- **dev** - a newer commit has landed on `main` than the one you built / pulled.

Click the pill to open the GitHub release for the changelog before upgrading. The commands to actually pull the update depend on how you installed:

=== "Prebuilt Docker (stable)"

    ```bash
    ./run-docker.sh --pull            # picks up the new :latest release
    # or pin a specific version:
    ./run-docker.sh --pull=v1.2.0
    ```

=== "Prebuilt Docker (dev)"

    ```bash
    ./run-docker.sh --pull=dev        # fetches the newest :dev image
    ```

=== "Local Docker (stable)"

    ```bash
    git fetch --tags
    git checkout "$(git tag --sort=-v:refname | head -1)"
    ./run-docker.sh --rebuild
    # add --no-cache for a fully fresh image, --prune to drop the old one
    ```

=== "Local Docker (dev)"

    ```bash
    git checkout main
    git pull
    ./run-docker.sh --rebuild
    ```

For standalone CLI installs, see [CLI Install &rarr; Updating](cli-install.md#updating).

Docker bind mounts (`cache/`, `config/`, `.env`, `browser.json`) persist across rebuilds and image swaps, so your data and credentials survive any upgrade path.

---

## Release channels

Which tag/branch you run determines whether you're on the **stable** or **dev** channel. The concept applies to all install paths (Docker and CLI) - see [Release Channels](channels.md) for the full table and how to switch.
