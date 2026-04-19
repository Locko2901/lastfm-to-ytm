# Last.fm &rarr; YouTube Music Playlist Creator

[![Made with Python](https://img.shields.io/badge/Made%20with-Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Built with ytmusicapi](https://img.shields.io/badge/Built%20with-ytmusicapi-FF0000?logo=youtube&logoColor=white)](https://ytmusicapi.readthedocs.io/)
[![Uses Last.fm API](https://img.shields.io/badge/Uses-Last.fm%20API-D51007?logo=last.fm&logoColor=white)](https://www.last.fm/api)
[![MIT License](https://img.shields.io/github/license/Locko2901/lastfm-to-ytm)](https://github.com/Locko2901/lastfm-to-ytm/blob/main/LICENSE)

Create and maintain a YouTube Music playlist from your Last.fm listening history. This tool fetches your recent scrobbles, intelligently finds matches on YouTube Music, and keeps a playlist updated. Optionally, it can snapshot your listening into weekly playlists.

![Dashboard Preview](screenshots/dashboard.png)

## Features

- Creates/updates a YouTube Music playlist from your Last.fm scrobbles
- Optional recency-weighted selection to prioritize what you've listened to lately
- Intelligent search and matching on YouTube Music:
    - Prefers official Songs over user-uploaded Videos
    - Handles artist variations and collaborations
    - Avoids common mismatches (covers, remixes, live versions) where possible
    - Considers title, artist, and album similarity
- Weekly playlist snapshots (e.g., *"Your Playlist week of 2026-03-09"*)
- **Custom tag playlists** - auto-generate genre/tag-based playlists from your Last.fm tags (e.g., "Breakcore Mix", "Chill Electronic")
- **Web dashboard** (Docker) with real-time sync console, settings editor, cache browser, override/blacklist management, and built-in scheduler
- Configurable via environment variables, `.env` file, or the web UI
- Safe, incremental updates with batching and rate-limit-friendly delays

## Two Ways to Run

| | Docker (recommended) | CLI-only |
|---|---|---|
| **What** | Web dashboard + sync engine | Sync engine only |
| **Config** | Web UI (or `.env`) | `.env` + JSON files |
| **Scheduling** | Built-in scheduler | cron / systemd / Task Scheduler |
| **Get started** | `./run-docker.sh` | `pip install . && python run.py` |

:material-arrow-right: **[Get started in 5 minutes](quickstart.md)**

## Explore

| Section | What you'll find |
|---|---|
| **[Getting Started](quickstart.md)** | Installation (Docker & CLI), configuration reference |
| **[Features](dashboard.md)** | Dashboard, tag playlists, overrides, webhooks, history, teleporter |
| **[How It Works](how-it-works.md)** | Search matching, recency weighting, weekly playlists |
| **[Troubleshooting](troubleshooting.md)** | Common problems and fixes |
| **[Development](development.md)** | Contributing, project structure, i18n, linting |
