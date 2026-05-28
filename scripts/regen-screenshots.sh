#!/usr/bin/env bash
# Regenerate every dashboard screenshot under docs/screenshots/.
#
# Uses the project venv (.venv) so Playwright + Chromium are isolated.
# Pass extra flags through to the underlying generator, e.g.:
#   ./scripts/regen-screenshots.sh --only settings_modal
#   ./scripts/regen-screenshots.sh --headed

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"

if [[ ! -x "${PY}" ]]; then
  echo "error: ${PY} not found." >&2
  echo "       Create the venv first:  python3 -m venv .venv && .venv/bin/pip install -e '.[web,dev,web-docs]'" >&2
  exit 1
fi

"${PY}" -m playwright install chromium >/dev/null

exec "${PY}" "${ROOT}/tests/screenshots/generate.py" --out "${ROOT}/docs/screenshots" "$@"
