# Last.fm &rarr; YouTube Music

**Your Last.fm listening history as a proper YouTube Music playlist.**

YouTube Music's built-in *Replay Mix* can't be shuffled - hit shuffle and you get one random track, then the rest play in their original order. This creates and maintains a real, editable playlist instead: it finds the right official upload for each track in your Last.fm history, and keeps the playlist in sync on a schedule you set. Optional weekly snapshots let you build an archive of your listening habits.

![Dashboard Preview](screenshots/dashboard.png)

<div class="grid cards" markdown>

-   :material-rocket-launch: **Get started in ~5 minutes**

    The Docker setup includes a web dashboard, a setup wizard, and a built-in scheduler. No terminal needed after install.

    [:material-arrow-right: Quick Start (Docker)](quickstart.md)

</div>

## Highlights

- **Web dashboard** to configure everything, browse your playlist, fix wrong matches, and watch syncs run live.
- **Smart matching** that prefers official Songs over user uploads and rejects nightcore, sped-up, slowed, 8D, etc.
- **Recency + play-count weighting** so the playlist reflects what you're *actually* listening to right now.
- **Weekly snapshot playlists** so you build a long-term archive of how your taste evolves.
- **Tag-based playlists** (e.g. "Breakcore Mix", "Chill Electronic") auto-filled from your Last.fm tags.
- **Built-in scheduler, webhooks, encrypted backup** - see the sidebar for everything else.

!!! info "Prefer not to use Docker?"
    There's a [standalone CLI install](cli-install.md) too. It runs the same sync engine; you handle scheduling yourself with cron/systemd. The Docker path is recommended for almost everyone.

---

<small>
[![Made with Python](https://img.shields.io/badge/Made%20with-Python-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Built with ytmusicapi](https://img.shields.io/badge/Built%20with-ytmusicapi-FF0000?logo=youtube&logoColor=white)](https://ytmusicapi.readthedocs.io/)
[![Uses Last.fm API](https://img.shields.io/badge/Uses-Last.fm%20API-D51007?logo=last.fm&logoColor=white)](https://www.last.fm/api)
[![MIT License](https://img.shields.io/github/license/Locko2901/lastfm-to-ytm)](https://github.com/Locko2901/lastfm-to-ytm/blob/main/LICENSE)
</small>
