#!/usr/bin/env bash
# Pre-commit helper: fix, format, lint, and update translations.
# Run from the repo root: ./precommit.sh
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
BOLD='\033[1m'
RESET='\033[0m'

step() { printf "\n${BOLD}==> %s${RESET}\n" "$1"; }
pass() { printf "${GREEN}  ✓ %s${RESET}\n" "$1"; }
fail() { printf "${RED}  ✗ %s${RESET}\n" "$1"; exit 1; }

# fix and format
step "Ruff: auto-fix"
.venv/bin/ruff check . --fix && pass "ruff check --fix" || fail "ruff check --fix"

step "Ruff: format"
.venv/bin/ruff format . && pass "ruff format" || fail "ruff format"

step "Biome: lint + fix"
npm run lint:fix && pass "biome check --write" || fail "biome check --write"

step "Biome: format"
npm run format && pass "biome format --write" || fail "biome format --write"

step "HTML templates: format (js-beautify)"
npm run format:templates && pass "format:templates" || fail "format:templates"

# lint checks
step "Ruff: lint check"
.venv/bin/ruff check . && pass "ruff check" || fail "ruff check"

step "Ruff: format check"
.venv/bin/ruff format . --check && pass "ruff format --check" || fail "ruff format --check"

step "Biome: lint check"
npm run lint && pass "biome check" || fail "biome check"

step "j2lint: template lint"
.venv/bin/j2lint web/templates --extensions html --ignore jinja-statements-indentation \
  && pass "j2lint" || fail "j2lint"

# translations
step "Babel: extract strings"
.venv/bin/pybabel extract -F babel.cfg -o web/translations/messages.pot . \
  && pass "pybabel extract" || fail "pybabel extract"

step "Babel: update catalogs"
.venv/bin/pybabel update -i web/translations/messages.pot -d web/translations \
  && pass "pybabel update" || fail "pybabel update"

step "Babel: compile catalogs"
.venv/bin/pybabel compile -d web/translations \
  && pass "pybabel compile" || fail "pybabel compile"

# end
printf "\n${GREEN}${BOLD}All checks passed!${RESET}\n"
