#!/usr/bin/env bash
# Regenerate every dashboard screenshot under docs/screenshots/ and the GitHub
# social preview card under docs/assets/.
#
# Uses the project venv (.venv) so Playwright + Chromium are isolated.
# Pass extra flags through to the underlying screenshot generator, e.g.:
#   ./scripts/regen-screenshots.sh --only settings_modal
#   ./scripts/regen-screenshots.sh --headed
# Skip the social preview with --no-social.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${ROOT}/.venv/bin/python"

if [[ ! -x "${PY}" ]]; then
  echo "error: ${PY} not found." >&2
  echo "       Create the venv first:  python3 -m venv .venv && .venv/bin/pip install -e '.[web,dev,web-docs]'" >&2
  exit 1
fi

social=1
args=()
for arg in "$@"; do
  if [[ "${arg}" == "--no-social" ]]; then
    social=0
  else
    args+=("${arg}")
  fi
done

"${PY}" -m playwright install chromium >/dev/null

if [[ "${social}" -eq 1 ]]; then
  "${PY}" "${ROOT}/scripts/gen_social_preview.py"
fi

exec "${PY}" "${ROOT}/tests/screenshots/generate.py" --out "${ROOT}/docs/screenshots" "${args[@]}"

