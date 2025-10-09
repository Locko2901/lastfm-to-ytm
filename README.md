[![Made with Python](https://img.shields.io/badge/Made%20with-Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Built with ytmusicapi](https://img.shields.io/badge/Built%20with-ytmusicapi-FF0000?logo=youtube&logoColor=white)](https://ytmusicapi.readthedocs.io/)
[![Uses Last.fm API](https://img.shields.io/badge/Uses-Last.fm%20API-D51007?logo=last.fm&logoColor=white)](https://www.last.fm/api)
[![MIT License](https://img.shields.io/github/license/Locko2901/lastfm-to-ytm)](LICENSE)

# Last.fm → YouTube Music Playlist Creator

Create and maintain a YouTube Music playlist from your Last.fm listening history. This tool fetches your recent scrobbles, intelligently finds matches on YouTube Music, and keeps a playlist updated. Optionally, it can snapshot your listening into weekly playlists (e.g., “Your Playlist Name week of YYYY-MM-DD”).

## Table of Contents
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Authentication](#authentication)
- [Configuration](#configuration)
- [Usage](#usage)
- [How It Works](#how-it-works)
- [Search and Matching](#search-and-matching)
- [Weekly Playlists](#weekly-playlists)
- [Scheduling (Optional)](#scheduling-optional)
- [Troubleshooting](#troubleshooting)
- [Credits](#credits)
- [License](#license)

## Features

- Creates/updates a YouTube Music playlist using your Last.fm scrobbles.
- Optional recency-weighted selection to prioritize what you’ve listened to lately.
- Intelligent search and matching on YouTube Music:
  - Prefers official Songs over user-uploaded Videos
  - Handles artist variations/collaborations
  - Avoids common mismatches (covers, remixes, live versions) where possible
  - Considers title, artist, and album similarity
- Weekly playlist snapshots: “Your Playlist Name week of YYYY-MM-DD”.
- Configurable via environment variables or a `.env` file.
- Safe, incremental updates with batching and rate-limit-friendly delays.

## Prerequisites

- Python 3.6+ installed.
- A Last.fm API key: https://www.last.fm/api
- YouTube Music authentication exported for ytmusicapi:
  - Setup guide: https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html

> Keep your `browser.json` private. Do not commit it.

## Installation

Clone the repo
```bash
git clone https://github.com/Locko2901/lastfm-to-ytm.git
cd lastfm-to-ytm
```

Create & activate a virtual environment
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

Install dependencies
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Authentication

### Last.fm
- Get an API key at https://www.last.fm/api
- Set `LASTFM_API_KEY` and `LASTFM_USER` in the `.env` file.

### YouTube Music (ytmusicapi)
- Export your auth following the ytmusicapi docs:
  - https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html
- This tool supports browser-based auth only (OAuth is not supported).

> Note: Anonymous search is supported (`USE_ANON_SEARCH=true`) for finding tracks, but you still need valid YouTube Music auth to create or update playlists.

## Configuration

Rename the example environment file and fill in your settings:

1. Rename `.env.example` to `.env`
2. Open `.env` in a text editor
3. Fill in your Last.fm username and API key
4. Adjust other settings as needed (playlist name, visibility, limits, etc.)
5. Save the file

## Usage

```bash
python run.py
```

## What happens:
- Updates or creates the main playlist named by `PLAYLIST_NAME`.
- If `WEEKLY_ENABLED=true`, also creates/updates the weekly playlist for the current week:
  - If `WEEKLY_PLAYLIST_PREFIX` is set:
    - “{WEEKLY_PLAYLIST_PREFIX} week of YYYY-MM-DD”
  - Otherwise:
    - “{PLAYLIST_NAME} week of YYYY-MM-DD”

> The tool manages only the playlist(s) it creates. Manual edits to those playlists are reverted on the next run to match the tool’s logic.

## How It Works

1) Fetch recent scrobbles from Last.fm  
2) Process tracks:
   - If `USE_RECENCY_WEIGHTING=true`, score each track using exponential decay (see below)
   - Otherwise, pick up to `LIMIT` most recent unique tracks
   - If `DEDUPLICATE=true`, ensure the final playlist does not include duplicates
3) Search YouTube Music for each track and choose the best match (see [Search and Matching](#search-and-matching))  
4) Create or update YouTube Music playlist(s) in batches (`CHUNK_SIZE`) with delays (`SLEEP_BETWEEN_SEARCHES`) to be rate-limit friendly

## Recency Weighting — Under the Hood

This tool uses a half-life–based exponential decay to rank tracks by how recently you listened to them, while still accounting for multiple plays.

- Per-play weight:
  - `weight = 0.5 ** (age_hours / half_life_hours)` (if `half_life_hours > 0`, else `1.0`)
  - More recent plays contribute more weight; a play exactly one half-life old contributes 0.5
- Per-track score:
  - Sum the weights of all scrobbles for that track
- Sorting priority:
  1) Higher total score
  2) More recent latest play (ts)
  3) Higher play count
- Case-insensitive aggregation by `(artist, track)`; album is updated from the latest-scrobbled non-empty album

## Search and Matching

The matching algorithm aims to select the “right” track:
- Prefers official Song results over user-uploaded Videos.
- Scores title, artist(s), and album similarity.
- Handles common artist variations and multi-artist collaborations.
- Avoids covers, remixes, and live versions unless they’re the closest available match.
- Can perform authenticated or anonymous search (`USE_ANON_SEARCH`), which may affect results.

If a track cannot be matched reliably, it may be skipped or a best-effort match may be used.

## Weekly Playlists

When `WEEKLY_ENABLED=true`, the tool creates/updates weekly playlists named:
- “{PLAYLIST_NAME} week of YYYY-MM-DD”, or
- “{WEEKLY_PLAYLIST_PREFIX} week of YYYY-MM-DD” if a prefix is set.

The date corresponds to the start of the week used by the tool. Over time, you’ll build a library of weekly snapshots.

## Scheduling (Optional but Encouraged)

#### This tool is meant to run on a scedule to keep the playlists up to date.

Cron (Linux/macOS):
```bash
crontab -e

# Example: run every day at 00:05
5 0 * * * cd /path/to/repo && /usr/bin/python3 run.py >> playlist.log 2>&1
```

systemd (Linux):
```bash
# /etc/systemd/system/lastfm-ytm.service
[Unit]
Description=Last.fm to YouTube Music Playlist Updater
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/path/to/repo
ExecStart=/usr/bin/python3 /path/to/repo/run.py

# /etc/systemd/system/lastfm-ytm.timer
[Unit]
Description=Run Last.fm to YTM updater daily

[Timer]
OnCalendar=*-*-* 00:05:00
Persistent=true

[Install]
WantedBy=timers.target
```

Windows Task Scheduler:
- Action: Start a program
- Program/script: path to `python.exe`
- Add arguments: `C:\path\to\repo\run.py`
- Start in: `C:\path\to\repo`
- Trigger: Daily at a time you prefer

## Troubleshooting

- YouTube Music auth errors:
  - Ensure `YTM_AUTH_PATH` points to a valid ytmusicapi JSON
  - Re-export credentials following the ytmusicapi setup guide
- Last.fm errors (401/403/invalid key):
  - Confirm `LASTFM_API_KEY` and `LASTFM_USER`
  - Verify your key at https://www.last.fm/api/accounts
- Playlist not updating:
  - Confirm `PLAYLIST_NAME` matches exactly
  - Set `LOG_LEVEL=DEBUG` for verbose output
- Missing or wrong matches:
  - Toggle `USE_ANON_SEARCH`
  - Increase `SLEEP_BETWEEN_SEARCHES` slightly
  - Some tracks may be region-restricted or unavailable on YouTube Music
- Rate limiting or throttling:
  - Increase `SLEEP_BETWEEN_SEARCHES`
  - Reduce `CHUNK_SIZE`
- Weekly date mismatches:
  - Time zones and UTC timestamps from Last.fm can shift what falls into a given week

## Credits

- [ytmusicapi](https://ytmusicapi.readthedocs.io/) — YouTube Music API wrapper
- Thanks to the Last.fm and YouTube Music communities.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
