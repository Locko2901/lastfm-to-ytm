[![CI](https://github.com/Locko2901/lastfm-to-ytm/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Locko2901/lastfm-to-ytm/actions/workflows/ci.yml)
[![Latest Release](https://img.shields.io/github/v/release/Locko2901/lastfm-to-ytm?logo=github)](https://github.com/Locko2901/lastfm-to-ytm/releases/latest)
[![GHCR Image](https://img.shields.io/badge/ghcr.io-lastfm--to--ytm-2496ED?logo=docker&logoColor=white)](https://github.com/Locko2901/lastfm-to-ytm/pkgs/container/lastfm-to-ytm)
[![Made with Python](https://img.shields.io/badge/Made%20with-Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Built with ytmusicapi](https://img.shields.io/badge/Built%20with-ytmusicapi-FF0000?logo=youtube&logoColor=white)](https://ytmusicapi.readthedocs.io/)
[![Uses Last.fm API](https://img.shields.io/badge/Uses-Last.fm%20API-D51007?logo=last.fm&logoColor=white)](https://www.last.fm/api)
[![MIT License](https://img.shields.io/github/license/Locko2901/lastfm-to-ytm)](LICENSE)

# Last.fm &rarr; YouTube Music Playlist Creator

Keeps a YouTube Music playlist in sync with your Last.fm listening history. Last.fm logs every track you play as a "scrobble" - this tool reads those, finds the right official upload on YouTube Music (skipping live versions, remixes, and nightcore), and updates the playlist automatically. Optional weekly snapshots archive how your taste changes over time.

![Dashboard Preview](docs/screenshots/dashboard.png)

## Features

**Playlist sync**

- Creates/updates a YouTube Music playlist from your Last.fm scrobbles
- Optional recency-weighted selection to prioritize what you've listened to lately
- Weekly playlist snapshots (e.g., *"Your Playlist week of 2026-03-09"*)
- Custom tag playlists - auto-generate genre/tag-based playlists from your Last.fm tags

**Search & matching**

- Prefers official Songs over user-uploaded Videos
- Handles artist variations, collaborations, and featuring clauses
- Avoids common mismatches (covers, remixes, live versions, nightcore, sped up, etc.)
- Considers title, artist, uploader, and album similarity
- Two-phase search: exact query first, then parallel fallback with query expansion

**Web dashboard** (Docker)

- Real-time sync console
- Settings editor, cache browser, override/blacklist management
- Built-in scheduler (interval or cron)
- Sync history database with audit trail
- Encrypted config backup/restore (Teleporter)
- Discord and generic webhook notifications
- Installable as a PWA

**Infrastructure**

- Smart caching minimizes API calls (search results, playlist state, and tag data are all cached)
- Configurable via environment variables, `.env` file, or the web UI
- Rate-limit-friendly with automatic retries and configurable delays
- Multi-language support

## Quick Start

| | Docker (recommended) | CLI-only |
|---|---|---|
| **What** | Web dashboard + sync engine | Sync engine only |
| **Config** | Web UI (or `.env`) | `.env` + JSON files |
| **Scheduling** | Built-in scheduler | cron / systemd / Task Scheduler |
| **Get started** | `./run-docker.sh` | `pip install . && python run.py` |

```bash
# Docker (recommended, prebuilt image - no git/build needed)
curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh | bash
cd lastfm-to-ytm && ./run-docker.sh --pull

# Docker (clone & build locally)
git clone https://github.com/Locko2901/lastfm-to-ytm.git
cd lastfm-to-ytm && ./run-docker.sh

# CLI-only
pip install . && python run.py
```

On first launch, the web dashboard walks you through setup - `.env` creation, Last.fm credentials, and YouTube Music auth.

## Documentation

Full documentation is available at **[locko2901.github.io/lastfm-to-ytm](https://locko2901.github.io/lastfm-to-ytm/)**.

**Getting started**

- [Quick Start](https://locko2901.github.io/lastfm-to-ytm/quickstart/) - Docker and CLI setup
- [Configuration](https://locko2901.github.io/lastfm-to-ytm/configuration/) - Full settings reference

**Features**

- [Web Dashboard](https://locko2901.github.io/lastfm-to-ytm/dashboard/) - UI features and scheduler
- [Custom Tag Playlists](https://locko2901.github.io/lastfm-to-ytm/tag-playlists/) - Genre-based auto-playlists
- [Search Overrides](https://locko2901.github.io/lastfm-to-ytm/overrides/) - Manual fixes and blacklisting
- [Webhooks](https://locko2901.github.io/lastfm-to-ytm/webhooks/) - Discord and generic notifications
- [History Database](https://locko2901.github.io/lastfm-to-ytm/history/) - Sync tracking and audit trail
- [Teleporter](https://locko2901.github.io/lastfm-to-ytm/teleporter/) - Encrypted config backup/restore

**Reference**

- [How It Works](https://locko2901.github.io/lastfm-to-ytm/how-it-works/) - Search, matching, and recency weighting
- [Troubleshooting](https://locko2901.github.io/lastfm-to-ytm/troubleshooting/) - Common problems and known issues
- [Development](https://locko2901.github.io/lastfm-to-ytm/development/) - Architecture, internals, and contributing

## Credits

- [ytmusicapi](https://ytmusicapi.readthedocs.io/) - YouTube Music API wrapper
- Thanks to the Last.fm and YouTube Music communities.

## License

MIT - see [LICENSE](LICENSE) for details.
