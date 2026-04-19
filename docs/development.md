# Development

## Setup

```bash
pip install -e ".[dev,web]"
```

---

## Project Structure

```
├── run.py                  # CLI entrypoint (main playlist sync)
├── run_tags.py             # CLI entrypoint (tag playlist sync)
├── src/                    # Core sync engine
│   ├── main.py             # Main orchestrator (run())
│   ├── config.py           # Settings from environment variables
│   ├── context.py          # RuntimeContext (shared dependencies)
│   ├── webhook.py          # Webhook notifications
│   ├── cache/              # Cache layer (search, playlist, tags)
│   ├── lastfm/             # Last.fm API client and scrobble fetching
│   ├── recency/            # Recency weighting algorithm
│   ├── search/             # YouTube Music search, scoring, and matching
│   ├── tags/               # Tag resolution, filtering, and tag playlist sync
│   ├── playlist/           # Playlist sync, diffing, weekly snapshots
│   ├── ytm/                # YouTube Music API wrapper
│   └── history/            # SQLite history database
├── web/                    # Flask web dashboard
│   ├── app.py              # Flask app factory
│   ├── routes/             # Route handlers (API, auth, sync, actions)
│   ├── services/           # Business logic (scheduler, state, teleporter)
│   ├── templates/          # Jinja2 HTML templates
│   ├── static/             # CSS, JS, icons
│   ├── translations/       # i18n catalogs
│   └── i18n/               # Custom Babel extractor for JS strings
├── config/                 # User config files (overrides, custom playlists)
├── cache/                  # Runtime caches (gitignored)
├── devops/                 # Docker setup (Dockerfile, compose, entrypoint)
└── docs/                   # This documentation (MkDocs)
```

---

## Credits

- [ytmusicapi](https://ytmusicapi.readthedocs.io/) - YouTube Music API wrapper
- Thanks to the Last.fm and YouTube Music communities.

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/Locko2901/lastfm-to-ytm/blob/main/LICENSE) file for details.
