# Contributing

Contributions are welcome. The tooling spans four languages (Python, JS, CSS, HTML templates) with a full stack of linters, formatters, type checking, and two test layers - but [`./precommit.sh`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/precommit.sh) wires it all together so you can run everything with one command.

## Reporting issues

- Use the [issue tracker](https://github.com/Locko2901/lastfm-to-ytm/issues).
- Include: what you tried, what happened, what you expected. Logs and `.env` settings (with secrets redacted) help a lot.

## Development setup

See [Development docs](https://locko2901.github.io/lastfm-to-ytm/development/) for the full setup. Short version:

```bash
pip install -e ".[dev,web,web-docs]"
npm install
python -m playwright install chromium
```

The `web-docs` extra and the Chromium download are what let `./precommit.sh` run the frontend (Playwright) layer; without them those tests skip rather than run.

uv users: `uv pip install -e ".[dev,web,web-docs]"` (after `uv venv`) works just the same.

## Pull requests

- Fork, branch off `main`, open a PR against `main`.
- Keep PRs focused - one logical change per PR.
- Run [`./precommit.sh`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/precommit.sh) before pushing. It runs Ruff, mypy, Biome, template formatting, both pytest layers (unit + frontend), updates translation catalogs, and regenerates the project structure tree in the docs.
- Add or update tests for logic changes where practical. See the [Testing docs](https://locko2901.github.io/lastfm-to-ytm/testing/) for what's covered and how the suite is laid out; pure-logic and cache/DB changes should come with unit tests, while API/network glue is still verified manually via `python run.py` or the web dashboard.

## Commit messages - required format

This repo uses **[Conventional Commits](https://www.conventionalcommits.org/)**. The release version, git tag, GitHub Release, and changelog are all generated from commit messages by [release-please](https://locko2901.github.io/lastfm-to-ytm/releases/). Non-conforming commits won't break anything but will be excluded from the changelog.

| Prefix | Use for | Bump (when highest in the batch) |
|---|---|---|
| `feat!:` / `fix!:` | breaking change (or add `BREAKING CHANGE:` footer) | **major** |
| `feat:` | new user-facing feature | minor |
| `fix:` | bug fix | patch |
| `perf:` | performance improvement | patch |
| `docs:` | documentation only | patch |
| `refactor:` | code change with no behavior change | patch |
| `style:` | formatting, no logic | patch |
| `test:` | tests | patch |
| `ci:` / `build:` | CI or build tooling | patch |
| `chore:` | misc maintenance | patch |
| `i18n:` | translation catalog updates | patch |

Any conventional commit ends up in a Release PR. If a batch contains a `feat:`, the bump is minor; if anything is breaking, major; otherwise patch. If you don't want a release yet, just don't merge the open Release PR - it keeps accumulating until you do.

Optional scope in parentheses, e.g. `feat(web): add cache modal`. See [Releases & Changelog](https://locko2901.github.io/lastfm-to-ytm/releases/) for full details on the release pipeline.

## Code style

- **Python**: Ruff (config in `pyproject.toml`). Line length 150. Static types checked with mypy in `strict` mode (`mypy`).
- **JS/CSS**: Biome (config in `biome.jsonc`).
- **HTML templates**: js-beautify via `npm run format:templates`.
- **Translations**: see [i18n docs](https://locko2901.github.io/lastfm-to-ytm/i18n/). Run `pybabel extract` + `pybabel update` when adding user-facing strings.

## License

By contributing, you agree your contributions are licensed under the [MIT License](https://github.com/Locko2901/lastfm-to-ytm/blob/main/LICENSE).
