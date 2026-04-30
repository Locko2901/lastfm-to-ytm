# Contributing

Contributions are welcome. The process is intentionally lightweight.

## Reporting issues

- Use the [issue tracker](https://github.com/Locko2901/lastfm-to-ytm/issues).
- Include: what you tried, what happened, what you expected. Logs and `.env` settings (with secrets redacted) help a lot.

## Development setup

See [Development docs](https://locko2901.github.io/lastfm-to-ytm/development/) for the full setup. Short version:

```bash
pip install -e ".[dev,web]"
npm install
```

## Pull requests

- Fork, branch off `main`, open a PR against `main`.
- Keep PRs focused - one logical change per PR.
- Run [`./precommit.sh`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/precommit.sh) before pushing. It runs Ruff, Biome, and template formatting.
- No tests exist yet; manual verification via `python run.py` or the web dashboard is expected.

## Commit messages - required format

This repo uses **[Conventional Commits](https://www.conventionalcommits.org/)**. The release version, git tag, GitHub Release, and changelog are all generated from commit messages by [release-please](https://locko2901.github.io/lastfm-to-ytm/releases/). Non-conforming commits won't break anything but will be excluded from the changelog.

| Prefix | Use for | Version effect |
|---|---|---|
| `feat:` | new user-facing feature | minor bump |
| `fix:` | bug fix | patch bump |
| `perf:` | performance improvement | patch bump |
| `feat!:` / `fix!:` | breaking change (or add `BREAKING CHANGE:` footer) | **major bump** |
| `docs:` | documentation only | no release |
| `refactor:` | code change with no behavior change | no release |
| `style:` | formatting, no logic | no release |
| `test:` | tests | no release |
| `ci:` / `build:` | CI or build tooling | no release |
| `chore:` | misc maintenance | no release |
| `i18n:` | translation catalog updates | no release |

Optional scope in parentheses, e.g. `feat(web): add cache modal`. See [Releases & Changelog](https://locko2901.github.io/lastfm-to-ytm/releases/) for full details on the release pipeline.

## Code style

- **Python**: Ruff (config in `pyproject.toml`). Line length 150.
- **JS/CSS**: Biome (config in `biome.jsonc`).
- **HTML templates**: js-beautify via `npm run format:templates`.
- **Translations**: see [i18n docs](https://locko2901.github.io/lastfm-to-ytm/i18n/). Run `pybabel extract` + `pybabel update` when adding user-facing strings.

## License

By contributing, you agree your contributions are licensed under the [MIT License](https://github.com/Locko2901/lastfm-to-ytm/blob/main/LICENSE).
