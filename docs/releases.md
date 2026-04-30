# Releases & Changelog

Versioning, the changelog, and GitHub Releases are fully automated via [release-please](https://github.com/googleapis/release-please).

## How it works

A GitHub Action ([.github/workflows/release-please.yml](https://github.com/Locko2901/lastfm-to-ytm/blob/main/.github/workflows/release-please.yml)) watches `main`. On every push it:

1. Parses commits since the last release tag.
2. Maintains a single rolling **Release PR** titled `chore(main): release X.Y.Z` that bumps the version and updates the changelog.
3. When that PR is merged, it automatically:
    - Tags `vX.Y.Z`
    - Creates a GitHub Release with the new changelog section as release notes
    - The merged PR already contains the bumped `pyproject.toml` and updated `CHANGELOG.md`

## Conventional Commits

The bot relies entirely on commit message prefixes:

| Prefix | Effect | Example bump (1.2.3 &rarr;) |
|---|---|---|
| `fix:` | patch release | 1.2.4 |
| `perf:` | patch release | 1.2.4 |
| `feat:` | minor release | 1.3.0 |
| `feat!:` / `fix!:` | **major** release | 2.0.0 |
| Footer `BREAKING CHANGE:` | **major** release | 2.0.0 |
| `chore:`, `docs:`, `refactor:`, `style:`, `test:`, `ci:`, `build:`, `i18n:` | no release | - |

Scopes are optional and shown in the changelog as bold prefixes:

```
feat(web): add cache management modal
fix(search): handle empty artist names
feat!: drop Python 3.10 support
```

## Workflow

1. Push conventional commits to `main` as you normally would.
2. The Release PR auto-updates with each push - **don't edit it**.
3. When ready to ship, merge the Release PR with the default title/description.
4. `git pull` locally to sync the bumped `pyproject.toml`, `CHANGELOG.md`, and `.release-please-manifest.json`.

## Files involved

- [`.release-please-config.json`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/.release-please-config.json) - bot config (Python release type, `pyproject.toml` extra-file mapping)
- [`.release-please-manifest.json`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/.release-please-manifest.json) - current version anchor (source of truth for the bot)
- [`CHANGELOG.md`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/CHANGELOG.md) - Keep-a-Changelog format, prepended to on each release
- [`cliff.toml`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/cliff.toml) - `git-cliff` config, kept around for ad-hoc regeneration of the historical changelog

## Repository setting required

GitHub &rarr; **Settings &rarr; Actions &rarr; General &rarr; Workflow permissions** &rarr; enable *"Allow GitHub Actions to create and approve pull requests"*. Without this, release-please cannot open the Release PR.

## Manual changelog regeneration (rare)

If the historical changelog ever needs to be rebuilt from scratch:

```bash
git-cliff --tag vX.Y.Z -o CHANGELOG.md
```

This is only needed for one-off seeds; release-please handles everything afterward.
