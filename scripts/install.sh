#!/usr/bin/env bash
#
# install.sh - One-line installer for lastfm-to-ytm (prebuilt Docker image).
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/Locko2901/lastfm-to-ytm/main/scripts/install.sh | bash -s -- my-dir
#
# Environment variables:
#   YTMT_REF    Git ref to download files from (default: latest release tag,
#               or 'main' if no release exists / GitHub API is unreachable).
#               Pass a tag like v1.2.0 to pin both the launcher and the
#               prebuilt image tag, or 'main' to track the dev channel.
#   YTMT_DIR    Target directory (default: lastfm-to-ytm, or $1).
#

set -euo pipefail

REPO="Locko2901/lastfm-to-ytm"
TARGET="${YTMT_DIR:-${1:-lastfm-to-ytm}}"

resolve_latest_ref() {
    local tag
    tag=$(curl -fsSL \
        -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/${REPO}/releases/latest" 2>/dev/null \
        | sed -n 's/.*"tag_name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
        | head -n1)
    if [[ -n "$tag" ]]; then
        echo "$tag"
    else
        echo "main"
    fi
}

REF="${YTMT_REF:-}"
RAW=""

if [[ -t 1 ]]; then
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    CYAN='\033[0;36m'
    RED='\033[0;31m'
    NC='\033[0m'
else
    GREEN='' YELLOW='' CYAN='' RED='' NC=''
fi

err() { echo -e "${RED}✗${NC} $*" >&2; exit 1; }

command -v curl >/dev/null 2>&1 || err "curl is required"
command -v docker >/dev/null 2>&1 || err "docker is required (see https://docs.docker.com/get-docker/)"

if [[ -z "$REF" ]]; then
    echo -e "${CYAN}Resolving latest release...${NC}"
    REF="$(resolve_latest_ref)"
    if [[ "$REF" == "main" ]]; then
        echo -e "  ${YELLOW}!${NC} GitHub API didn't return a release; falling back to 'main'"
    else
        echo -e "  ${GREEN}✓${NC} latest release: ${REF}"
    fi
fi
RAW="https://raw.githubusercontent.com/${REPO}/${REF}"

if [[ -e "$TARGET" && -n "$(ls -A "$TARGET" 2>/dev/null || true)" ]]; then
    err "target directory '$TARGET' already exists and is not empty"
fi

echo -e "${CYAN}Installing lastfm-to-ytm into ./${TARGET} (ref: ${REF})${NC}"
mkdir -p "$TARGET/devops"

fetch() {
    local src="$1" dst="$2"
    echo -e "  ${YELLOW}→${NC} ${src}"
    curl -fsSL "${RAW}/${src}" -o "${TARGET}/${dst}" \
        || err "failed to download ${src} (ref '${REF}' may not exist)"
}

fetch "run-docker.sh"             "run-docker.sh"
fetch "devops/docker-compose.yml" "devops/docker-compose.yml"
fetch ".env.example"              ".env.example"

chmod +x "${TARGET}/run-docker.sh"

# Pin the image tag to the requested ref when it looks like a release tag.
# Otherwise the launcher's default 'latest' is used.
PULL_FLAG="--pull"
if [[ "$REF" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    PULL_FLAG="--pull=${REF}"
fi

echo
echo -e "${GREEN}✓ Installed.${NC}"
echo
echo -e "${CYAN}Next steps:${NC}"
echo "  cd ${TARGET}"
echo "  ./run-docker.sh ${PULL_FLAG}"
echo
echo -e "Then open ${GREEN}http://localhost:2002${NC} and follow the setup wizard."
