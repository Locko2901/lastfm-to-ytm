# Releases & Changelog

Versioning, the changelog, and GitHub Releases are fully automated via [release-please](https://github.com/googleapis/release-please).

!!! warning "One-time setup required"
    Enable **Settings &rarr; Actions &rarr; General &rarr; Workflow permissions &rarr; "Allow GitHub Actions to create and approve pull requests"** in your fork/repo. Without this, release-please cannot open the Release PR and tagging never happens. See [Repository setting required](#repository-setting-required) below.

## How it works

The `release-please` job in [.github/workflows/ci.yml](https://github.com/Locko2901/lastfm-to-ytm/blob/main/.github/workflows/ci.yml) watches `main`. It only runs after all lint jobs in the same workflow pass, so a broken build can never tag a release. On every successful push to `main` it:

1. Parses commits since the last release tag.
2. Maintains a single rolling **Release PR** titled `chore(main): release X.Y.Z` that bumps the version and updates the changelog.
3. When that PR is merged, it automatically:
    - Tags `vX.Y.Z`
    - Creates a GitHub Release with the new changelog section as release notes
    - The merged PR already contains the bumped `pyproject.toml` and updated `CHANGELOG.md`

## Conventional Commits

The bot relies entirely on commit message prefixes. The **highest** bump in the batch wins:

| Prefix | Bump applied if it's the highest in the batch | Example (1.2.3 &rarr;) |
|---|---|---|
| `feat!:` / `fix!:` / `BREAKING CHANGE:` footer | **major** | 2.0.0 |
| `feat:` | minor | 1.3.0 |
| `fix:`, `perf:` | patch | 1.2.4 |
| `docs:`, `refactor:`, `style:`, `test:`, `ci:`, `build:`, `chore:`, `i18n:` | patch (only if nothing higher in the batch) | 1.2.4 |

In practice: any conventional commit will eventually result in a release PR. If a batch contains only `docs:`/`chore:`/etc., release-please cuts a patch release with those entries in the changelog. If you don't want to release yet, just don't merge the Release PR - it keeps accumulating commits until you do.

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

## Docker images

Tagging a release also fires the `docker-publish` job in [`ci.yml`](https://github.com/Locko2901/lastfm-to-ytm/blob/main/.github/workflows/ci.yml), which pushes a multi-arch image to `ghcr.io/locko2901/lastfm-to-ytm` with `:vX.Y.Z`, `:X.Y`, `:X`, and `:latest` tags - the stable channel. Untagged pushes to `main` publish a separate development channel (`:dev`, `:sha-<short>`) so `:latest` never points at an unreleased commit. The publish step runs after the linters and gates `release-please`, so a failed image build blocks the release tag. See [Docker Internals](docker-internals.md#published-images-ghcr).

## Build identification & the version pill

The dashboard's version pill distinguishes **stable** builds (running a tagged release) from **dev** builds (running anything else). The channel is decided at launch from observable state - no SHA comparison required - with the following precedence:

1. `YTMT_CHANNEL=stable|dev` environment variable (manual override).
2. `.channel` pointer file in the project root (written on every launch by `run-docker.sh`).
3. Git probe: HEAD is **detached on a release tag** &rarr; stable, otherwise &rarr; dev. Only used when neither of the above is present (i.e. standalone runs).

How each install populates the signal:

- **Prebuilt Docker** (`./run-docker.sh --pull[=TAG]`) - launcher writes `.channel` based on the requested tag (empty / `latest` / `vX.Y.Z` &rarr; stable; anything else &rarr; dev).
- **Local Docker build** (`./run-docker.sh`) - launcher writes `.channel` based on the git probe (detached on a tag &rarr; stable, else dev).
- **Standalone** (`python run.py`) - no launcher; the dashboard runs the git probe at request time.

| State | Pill label | Update arrow appears when |
|---|---|---|
| Stable | `v1.3.1` | A newer release tag exists |
| Dev | `dev·abc1234` | The default branch HEAD differs from the build's SHA (new release **or** new commit) |

Note that a plain `git clone` (or `git checkout main`) leaves HEAD attached to the branch and is always classified as **dev**, even when the branch tip happens to be a release commit. To be on stable you have to explicitly `git checkout vX.Y.Z`.

`COMMIT_SHA` (used for the SHA shown in the dev pill and for the dev update arrow) is populated by:

- CI (`docker-publish` job) &rarr; `${{ github.sha }}` for both stable and dev images
- `run-docker.sh` &rarr; `git rev-parse HEAD` of the local checkout
- Standalone runs &rarr; no file; the app falls back to `git rev-parse HEAD` of the working tree at runtime

## Upgrading

See [Updating](docker-reference.md#updating) for the per-install upgrade commands (CLI users: [CLI Install &rarr; Updating](cli-install.md#updating)).

## Manual changelog regeneration (rare)

If the historical changelog ever needs to be rebuilt from scratch:

```bash
git-cliff --tag vX.Y.Z -o CHANGELOG.md
```

This is only needed for one-off seeds; release-please handles everything afterward.
