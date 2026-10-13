# Portainer / Unraid (Compose)

Managing your containers from a web UI like Portainer or Unraid? Skip the installer: paste the compose file below into your stack editor and deploy. It runs the same prebuilt image as `./run-docker.sh --pull`, and the setup wizard takes it from there.

## Why the extra `init` service?

The app keeps its settings in two files, `.env` and `browser.json`, and they're mounted into the container one file at a time. If a mounted file doesn't exist on the host yet, Docker creates an empty **folder** in its place, and the container fails on startup with:

```text
rm: cannot remove '/app/.env': Device or resource busy
```

The installer and `run-docker.sh` avoid this by creating both files before the container starts. The `lastfm-to-ytm-init` service does the same job inside the stack: it runs for a second on each deploy, creates whichever file is missing (replacing the empty folder a failed deploy left behind), and exits. Files that already exist are never touched.

## The compose file

On Unraid it works as-is. Anywhere else, change the folder path first (see [What to change](#what-to-change)).

```yaml
services:
  # Runs once on every deploy, then exits ("Exited (0)" is expected).
  # Creates .env and browser.json as files, so Docker doesn't mount them as folders.
  lastfm-to-ytm-init:
    image: ghcr.io/locko2901/lastfm-to-ytm:latest
    container_name: lastfm-to-ytm-init
    restart: "no"
    entrypoint: ["sh", "-c"]
    command:
      - |
        set -e
        cd /data
        for f in .env browser.json; do
          if [ -d "$$f" ]; then rmdir "$$f"; fi
        done
        [ -f .env ] || touch .env
        [ -f browser.json ] || echo '{}' > browser.json
    volumes:
      - /mnt/user/appdata/lastfm-to-ytm:/data

  lastfm-to-ytm:
    image: ghcr.io/locko2901/lastfm-to-ytm:latest
    container_name: lastfm-to-ytm
    restart: unless-stopped
    depends_on:
      lastfm-to-ytm-init:
        condition: service_completed_successfully
    ports:
      - "2002:2002"
    environment:
      - TZ=Etc/UTC            # your timezone, e.g. Europe/Berlin
      - YTMT_CHANNEL=stable   # "dev" if you use the :dev image
    volumes:
      - /mnt/user/appdata/lastfm-to-ytm/runtime:/app/runtime
      - /mnt/user/appdata/lastfm-to-ytm/config:/app/config
      - /mnt/user/appdata/lastfm-to-ytm/.env:/app/.env
      - /mnt/user/appdata/lastfm-to-ytm/browser.json:/app/browser.json
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:2002/api/healthz"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 128M
```

### What to change

| What | Default | Change it when |
|---|---|---|
| `/mnt/user/appdata/lastfm-to-ytm` (5 places) | Unraid's appdata share | You're not on Unraid. Use any **absolute** folder on the host, e.g. `/opt/lastfm-to-ytm` - Docker creates it on the first deploy. |
| `"2002:2002"` | Dashboard on port 2002 | Port 2002 is taken. Change only the **left** number, e.g. `"8080:2002"`. |
| `TZ` | `Etc/UTC` | You're not on UTC. Scheduled syncs and log timestamps follow it. Use a tz database name like `Europe/Berlin` or `America/New_York`. |
| Image tag | `latest` (newest stable release) | You want to pin a release (`v1.2.0`) or run `dev`. Change both `image:` lines and set `YTMT_CHANNEL` to match - see [Release Channels](channels.md). |

The same tags are mirrored to Docker Hub as `lockooo/lastfm-to-ytm`, if you'd rather pull from there than GHCR.

## Deploy

=== "Portainer"

    1. **Stacks** &rarr; **Add stack**, and name it `lastfm-to-ytm`.
    2. Choose **Web editor** and paste the compose file.
    3. Replace `/mnt/user/appdata/lastfm-to-ytm` with an absolute path on the Docker host, e.g. `/opt/lastfm-to-ytm`. Avoid relative paths like `./data`: Portainer resolves them against its internal stack folder, so your data ends up somewhere hard to find.
    4. Click **Deploy the stack**.

=== "Unraid"

    1. Install the **Compose Manager** plugin from the **Apps** tab, if you don't have it yet.
    2. On the **Docker** tab, scroll down to the compose section and click **Add New Stack**. Name it `lastfm-to-ytm`.
    3. Click the stack's gear icon &rarr; **Edit Stack** &rarr; **Compose File**, paste the compose file, and save. The paths already point at `/mnt/user/appdata/lastfm-to-ytm`.
    4. Click **Compose Up**.

Then open `http://<server-ip>:2002` and follow the setup wizard - from here on it's the same as [Quick Start &rarr; Open the dashboard](quickstart.md#3-open-the-dashboard).

!!! note "`lastfm-to-ytm-init` shows as stopped"
    That's expected: it exits as soon as the files exist (status **Exited (0)**). Leave it in the stack - it runs again on every deploy and update.

## Updating

The version pill in the dashboard header lights up when a new release is out. To update, redeploy the stack with a fresh image pull:

- **Portainer:** open the stack, click **Update the stack**, and turn on **Re-pull image and redeploy**.
- **Unraid:** click **Update Stack** on the stack.

Settings, YouTube Music auth, and history all live in the folder you mounted, so they survive the update.
