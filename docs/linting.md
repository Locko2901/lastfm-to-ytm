# Linting & Formatting

This project uses these tools across its file types:

| Language | Tool | Config | VS Code extension |
|---|---|---|---|
| Python (lint/format) | [Ruff](https://docs.astral.sh/ruff/) | `pyproject.toml &rarr; [tool.ruff]` | `charliermarsh.ruff` |
| Python (static types) | [mypy](https://mypy.readthedocs.io/) | `pyproject.toml &rarr; [tool.mypy]` | `ms-python.mypy-type-checker` |
| JS / CSS | [Biome](https://biomejs.dev/) | `biome.jsonc` | `biomejs.biome` |
| HTML templates (lint) | [j2lint](https://github.com/aristanetworks/j2lint) | `pyproject.toml &rarr; [tool.j2lint]` | - (CLI only) |
| HTML templates (format) | [js-beautify](https://github.com/beautifier/js-beautify) | `package.json` script args + `--templating django` | `vscode.html-language-features` |

## Quick Reference

```bash
# Python
ruff check .           # lint
ruff check . --fix     # lint + auto-fix
ruff format .          # format
mypy                   # static type check (config picks up src/ + web/ + entry scripts)

# JS / CSS  (requires: npm install)
npm run lint           # lint
npm run lint:fix       # lint + fix
npm run lint:fix:unsafe  # lint + fix (safe + unsafe)
npm run format         # format only

# HTML templates - lint
j2lint web/templates --extensions html --ignore jinja-statements-indentation

# HTML templates - format  (requires: npm install)
npm run format:templates
```

## VS Code Setup

Install the recommended extensions (listed below), then:

- **Python** - Ruff formats and fixes imports on save.
- **JS / CSS** - Biome formats and organizes imports on save.
- **HTML** - formatted on save by VS Code's built-in HTML formatter (`vscode.html-language-features`, which uses js-beautify). The `html.format.templating` setting is enabled so the formatter preserves Jinja2 `{% %}` / `{{ }}` tags intact. Biome can't be used here because its HTML parser panics on Jinja2 `{% %}` block tags. Linting is still j2lint via CLI.

Biome is also told to only process `web/static/**` (via `files.includes` in `biome.jsonc`), so it will never touch Python files, config files, or HTML templates regardless of the VS Code setting.

## Ruff Rules

Configured in `pyproject.toml` under `[tool.ruff.lint]`. Highlights:

- Google-style docstrings (`pydocstyle` with `convention = "google"`)
- Import sorting (`isort`-compatible via the `I` ruleset)
- `T20` (no `print`) - except `run.py`, which is the CLI entrypoint
- `ARG001` ignored in `src/lastfm/fetch.py` - its signature must match `socket.getaddrinfo`

## mypy Rules

Configured in `pyproject.toml` under `[tool.mypy]`. Runs in `strict` mode (plus `warn_unreachable`) over `src/`, `web/`, `run.py`, and `run_tags.py`. Untyped third-party packages without stubs (`ytmusicapi`, `flask_babel`, `apscheduler`, `text_unidecode`, `unidecode`) are allowed via per-module `ignore_missing_imports` overrides. Run `mypy` with no arguments - the config picks up the right files.

## Biome Rules

Configured in `biome.jsonc`. Scope is strictly `web/static/**`.

Formatter uses 2-space indent, 150-char line width (matching Ruff), no semicolons, trailing commas.

Rule severity rationale is documented inline as comments in `biome.jsonc`.

## j2lint Rules

Only `S4` (statement indentation) is ignored - it expects pure-Jinja nesting levels, not the surrounding HTML context, producing false positives on every indented Jinja tag. Since j2lint doesn't support config-file ignore for CLI runs, `S4` is also passed via `--ignore` in CI.

## Pre-commit Script

The repo includes a convenience script that runs every linting, formatting, and i18n step in one go:

```bash
./precommit.sh
```

It runs the following in order (aborting on the first failure):

1. **Fix & format** - Ruff auto-fix, Ruff format, Biome lint+fix, Biome format, js-beautify templates
2. **Lint checks** - Ruff lint, Ruff format check, mypy, Biome lint, j2lint templates
3. **Translations** - Babel extract, update, and compile translation catalogs

This saves you from running all the individual commands listed above. Run it before committing to make sure everything is clean.

## CI

All three linters (+ HTML formatter) run on every push/PR via `.github/workflows/ci.yml` (the same workflow that gates `release-please`).
Jobs run in parallel; all must pass before merging.

| Job | Command |
|---|---|
| **python** | `ruff check` + `ruff format --check` |
| **types** | `mypy` |
| **js-css** | `npm ci && npm run lint` |
| **templates-lint** | `j2lint web/templates --extensions html --ignore jinja-statements-indentation` |
| **templates-format** | `npm run format:templates` |
