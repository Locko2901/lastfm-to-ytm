# Quick Start

Get from "fresh install" to "playlist syncing on YouTube Music" in about 5 minutes.

!!! note "Terminology"
    **YTM** = YouTube Music. **Scrobble** = a track Last.fm has logged you listening to. **Sync** = one full run that fetches scrobbles &rarr; resolves to YTM video IDs &rarr; updates the playlist.

This page covers the recommended **Docker** install. If you don't want to use Docker, see [CLI Install](cli-install.md) instead.

## Prerequisites

- **Docker** - if you don't have it yet, install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or [Docker Engine](https://docs.docker.com/engine/install/) (Linux). That's all you need; you won't have to type any `docker` commands yourself.
- A **Last.fm** account - [create a free API key](https://www.last.fm/api/account/create). The setup wizard will paste-prompt you for it.
- A **YouTube Music** account, signed in to any browser. The setup wizard walks you through copying auth from your browser's DevTools step by step.


---

## 1. Install

The installer downloads just the launcher, the compose file, and `.env.example`, then pulls the prebuilt multi-arch image from GHCR. By default it pins to the **latest stable release** ([what's stable vs. dev?](channels.md)).

=== "One-liner (recommended)"

    ```bash
    curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh | bash
    cd lastfm-to-ytm
    ```

=== "Inspect the script first"

    ```bash
    curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh -o install.sh
    less install.sh
    bash install.sh
    cd lastfm-to-ytm
    ```

!!! info "Want to build the image yourself?"
    If you'd rather clone the repo and build locally, see [Docker Reference &rarr; Building from source](docker-reference.md#building-from-source-clone-the-repo).
??? info "Pick a target directory, pin a release, or track the dev channel"

    Want a different target directory? Pass it as an argument:

    ```bash
    curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh | bash -s -- my-ytmt
    ```

    Pin a specific tag, or track the bleeding edge, by passing `YTMT_REF`:

    ```bash
    # Pin to a specific tag
    curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh \
        | YTMT_REF=v1.2.0 bash
    cd lastfm-to-ytm
    ./run-docker.sh --pull=v1.2.0

    # Track the bleeding edge instead
    curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh \
        | YTMT_REF=main bash
    cd lastfm-to-ytm
    ./run-docker.sh --pull=dev
    ```

    See [Release Channels](channels.md) for the difference.

## 2. Launch

The installer ends by printing the exact command to copy - it looks like `./run-docker.sh --pull=v1.2.0`. Paste it and press Enter.

If you missed the printout, this also works (pulls the most recent stable release):

```bash
./run-docker.sh --pull
```

## 3. Open the dashboard

Visit <http://localhost:2002> (or `http://<your-server-ip>:2002` from another machine).

The **first-launch setup wizard** walks you through:

1. Entering your **Last.fm** username + API key
2. Pasting **YouTube Music** auth (the wizard tells you exactly which DevTools headers to copy - same idea as `ytmusicapi browser`)
3. Reviewing the main settings and running your first sync

That's it - you're done.

---

## Verifying your first sync

When the sync finishes successfully you should see:

- A **successful** result in the dashboard's sync console
- A new playlist on YouTube Music named after `PLAYLIST_NAME` (default: `Last.fm Recents (auto)`)
- Tracks populated under the **Playlist** tab, with any unmatched ones surfaced under the **Not Found** tab

!!! question "First sync failed? Quick triage."

    Check the sync console output, or follow the container logs with `./run-docker.sh --logs`, and look at the first error line. The usual suspects:

    | Symptom | Likely cause | Fix |
    |---|---|---|
    | `401` from YouTube Music | `browser.json` invalid / expired | Re-run **YouTube Music Auth** from the Settings modal (gear icon) |
    | `403` or Last.fm error | API key wrong or missing | Re-check Last.fm fields in the Settings modal |
    | `AUTO_SYNC_CRON` parse error | Invalid cron expression | Use the placeholder, e.g. `0 */6 * * *` (every 6h) |
    | Empty playlist | No recent scrobbles to fetch | Scrobble something - default window is your recent listens |
    | Container won't start | Port `2002` in use | Set `YTMT_PORT` in `.env` (see [Docker reference](docker-reference.md#environment-variables-host-side)) |

    More patterns: [Troubleshooting](troubleshooting.md).

---

## What's Next?

After your first successful sync:

- **Fix mismatches** - check the playlist for wrong matches and add [manual overrides](overrides.md) to fix them. The web dashboard's **Not Found** and **Playlist** tabs make this easy.
- **Tune the playlist feel** - adjust `RECENCY_PLAY_WEIGHT`, `RECENCY_HALF_LIFE_HOURS`, or `LIMIT` from the Settings modal. Defaults are sensible; see [Configuration](configuration.md) only if you want to dig in.
- **Get weekly snapshots** - weekly playlists are on by default. Read [How It Works &rarr; Weekly Playlists](how-it-works.md#weekly-playlists) to learn how to rename or keep more.
- **Set up custom playlists** - auto-generate tag- or artist-based playlists from your Last.fm data. See [Custom Playlists](tag-playlists.md).
- **Enable scheduling** - turn on the built-in scheduler from the Settings modal (gear icon, top right).
- **Get notified** - set up [webhooks](webhooks.md) for Discord (or any other) notifications on sync results.

For day-to-day operations (start/stop/logs, updating, switching channels, pinning a release), see the [Docker reference](docker-reference.md).
