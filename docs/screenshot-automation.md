# Screenshot Automation

Every dashboard screenshot in these docs is generated deterministically by a
Playwright script that drives a Flask subprocess wired to a fixture cache.
There is no real Last.fm or YouTube Music traffic, no real credentials, and
no real clock  re-running the script produces byte-identical PNGs.

The whole pipeline is additive: no application code is modified, and the
generator lives entirely under [`tests/screenshots/`](https://github.com/Locko2901/lastfm-to-ytm/tree/main/tests/screenshots).

## Regenerate everything

From the project root, with the venv created:

```bash
./scripts/regen-screenshots.sh
```

That wrapper:

1. Confirms `.venv/bin/python` exists (create one with `pip install -e '.[web,dev,web-docs]'` if missing).
2. Downloads the Chromium browser (`playwright install chromium`) - a one-time step after installing the `web-docs` extra.
3. Runs `tests/screenshots/generate.py --out docs/screenshots`.

Pass any generator flag through, for example:

```bash
./scripts/regen-screenshots.sh --only settings_modal
./scripts/regen-screenshots.sh --headed --keep-server
```

## Generator flags

| Flag             | Default            | Description                                  |
| ---------------- | ------------------ | -------------------------------------------- |
| `--out DIR`      | `docs/screenshots` | Output directory                             |
| `--only NAME`    | _(all)_            | Capture a single target; repeatable          |
| `--port N`       | _(random free)_    | Pin the demo Flask port                      |
| `--headed`       | off                | Run Chromium headed (debugging)              |
| `--keep-server`  | off                | Leave the demo server running after captures |

## What gets captured

| Name               | File                     | UI state                                                   |
| ------------------ | ------------------------ | ---------------------------------------------------------- |
| `dashboard`        | `dashboard.png`          | Default Playlist tab with fixture tracks and stats         |
| `notfound`         | `notfound.png`           | "Not Found" tab populated from null-`video_id` cache rows  |
| `overrides`        | `overrides.png`          | Overrides + blacklist tab                                  |
| `custom_playlists` | `custom_playlists.png`   | Custom playlists tab                                   |
| `history`          | `history.png`            | History tab with seeded stats / charts                     |
| `settings_modal`   | `settings_modal.png`     | Settings modal (demo credentials only)                     |
| `setup_wizard`     | `setup_wizard.png`       | First-time setup wizard                                    |
| `teleporter`       | `teleporter.png`         | Teleporter export/import modal                             |
| `sync_console`     | `sync_console.png`       | Sync drawer with a realistic canned run log                |

## How it works

1. **Fixture cache**  `tests/screenshots/fixtures/` holds hand-curated
   `cache/*.json`, `config/*.json`, and a freshly seeded SQLite history DB
   (regenerated each run via the real `HistoryDB` schema).
2. **Subprocess server**  `generate.py` spawns
   [`tests/screenshots/_serve.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/tests/screenshots/_serve.py)
   with every `CACHE_*_FILE`, `TAG_*_FILE`, `CUSTOM_PLAYLISTS_FILE`, and
   `HISTORY_DB_FILE` env var pointed at the fixtures. These per-file
   overrides are required because the project `.env` may set them with
   relative paths that would otherwise shadow `CACHE_DIR` / `CONFIG_DIR`.
3. **Route stubs**  Playwright intercepts the volatile JSON endpoints
   (`/api/now-playing`, `/api/scheduler/status`, `/api/update-status`,
   `/api/failure_log`, `/api/auth/status`, `/api/auth/validate`,
   `/api/setup/status`, `/api/settings`) and serves canned payloads. This
   is what keeps the settings modal from ever rendering real credentials,
   even on a developer machine with a live `.env`.
4. **Frozen clock**  an init script monkey-patches `globalThis.Date` and
   `Date.now()` to a fixed instant (`2026-05-28T10:00:00Z`), so relative
   time labels ("45 minutes ago") don't drift between regenerations.
5. **UI driving**  tabs and modals are opened by calling the dashboard's
   own `window.*` entry points (`switchTab`, `showSettingsModal`,
   `openSyncDrawer`, `showSetupWizard`, `showTeleporterModal`) instead of
   clicking elements. That keeps captures resilient to layout changes.

## Adding a new capture

1. If it's a **tab**, add `(name, tab_id)` to `_TAB_CAPTURES` in
   [`generate.py`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/tests/screenshots/generate.py).
2. If it's a **modal**, add `(name, js_open_call, visible_selector)` to
   `_MODAL_CAPTURES`.
3. For anything bespoke (interactive flows, scrolling, fake data injection),
   write a dedicated `capture_<name>(context, base_url, out)` function and
   add it to the `CAPTURES` dict at the bottom.
4. If the new view needs data not present in
   [`tests/screenshots/fixtures/`](https://github.com/Locko2901/lastfm-to-ytm/tree/main/tests/screenshots/fixtures),
   extend the existing JSON / SQL seed  don't add new files unless
   necessary.
5. If the view talks to a volatile endpoint, add a stub to `ROUTE_STUBS`.
   Letting the real handler run is the most common cause of "this
   screenshot keeps changing".

## Troubleshooting

- **`libatk-1.0.so.0: cannot open shared object file`** (Linux only)  run
  `sudo .venv/bin/python -m playwright install-deps chromium`. The wrapper
  script only downloads the Chromium binary; the system shared libraries
  it depends on must be installed separately (and that step needs sudo).
- **Stats / counts don't match the fixture**  the real `.env` is leaking
  through. Confirm with `grep CACHE_ .env`; every `CACHE_*_FILE` setting
  must be overridden in `start_server()`'s env block.
- **Settings modal shows your real username / API key**  the
  `/api/settings`, `/api/auth/status`, or `/api/setup/status` stubs are
  missing or malformed; see `ROUTE_STUBS` in `generate.py`.
- **Server "didn't come up"**  bump the `start_server()` timeout, or run
  with `--keep-server --headed` to poke at it manually in a browser.
