#!/usr/bin/env bash
#
# run-docker.sh - Build and run the lastfm-to-ytm web dashboard in Docker
#
# Usage: ./run-docker.sh [OPTIONS]
#   --rebuild, -r    Force rebuild the Docker image
#   --no-cache       Rebuild without using Docker cache (forces fresh install)
#   --stop           Stop the running container
#   --logs, -l       Follow container logs
#   --status         Show container status
#   --help, -h       Show this help message
#

set -euo pipefail

if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    CYAN='\033[0;36m'
    NC='\033[0m' # No Color
else
    RED='' GREEN='' YELLOW='' BLUE='' CYAN='' NC=''
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEVOPS_DIR="$SCRIPT_DIR/devops"
COMPOSE_FILE="$DEVOPS_DIR/docker-compose.yml"
IMAGE_NAME="lastfm-to-ytm-web"
CONTAINER_NAME="lastfm-to-ytm"
PORT="${YTMT_PORT:-2002}"
HEALTH_TIMEOUT="${YTMT_HEALTH_TIMEOUT:-30}"

REBUILD=false
NO_CACHE=false
PRUNE=false
PRUNE_ALL=false
ACTION="start"  # default
for arg in "$@"; do
    case $arg in
        --rebuild|-r)
            REBUILD=true
            ;;
        --no-cache)
            REBUILD=true
            NO_CACHE=true
            ;;
        --stop)
            ACTION="stop"
            ;;
        --logs|-l)
            ACTION="logs"
            ;;
        --status)
            ACTION="status"
            ;;
        --prune)
            PRUNE=true
            ;;
        --prune-all)
            PRUNE=true
            PRUNE_ALL=true
            ;;
        --help|-h)
            echo "Usage: ./run-docker.sh [OPTIONS]"
            echo
            echo "Options:"
            echo "  --rebuild, -r    Force rebuild the Docker image"
            echo "  --no-cache       Rebuild without using Docker cache (implies --rebuild)"
            echo "  --stop           Stop the running container"
            echo "  --logs, -l       Follow container logs"
            echo "  --status         Show container status"
            echo "  --prune          Remove dangling images and old project images"
            echo "  --prune-all      Aggressive cleanup: also clear build cache and unused images"
            echo "                   Can be combined with --rebuild/--no-cache"
            echo "  --help, -h       Show this help message"
            echo
            echo "Environment variables:"
            echo "  YTMT_PORT            Port to expose (default: 2002)"
            echo "  YTMT_HEALTH_TIMEOUT  Seconds to wait for health check (default: 30)"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $arg${NC}"
            echo "Use --help for usage information."
            exit 1
            ;;
    esac
done

do_prune() {
    if [[ "$PRUNE_ALL" == true ]]; then
        echo -e "${CYAN}Pruning Docker resources (aggressive mode)...${NC}"
    else
        echo -e "${CYAN}Pruning Docker resources...${NC}"
    fi

    DANGLING=$(docker images -f "dangling=true" -q 2>/dev/null)
    if [[ -n "$DANGLING" ]]; then
        echo -e "${YELLOW}→ Removing dangling images...${NC}"
        docker rmi $DANGLING 2>/dev/null || true
        echo -e "${GREEN}✓ Dangling images removed${NC}"
    else
        echo -e "${GREEN}✓ No dangling images${NC}"
    fi

    OLD_IMAGES=$(docker images "$IMAGE_NAME" --format '{{.ID}}' | tail -n +2)
    if [[ -n "$OLD_IMAGES" ]]; then
        echo -e "${YELLOW}→ Removing old $IMAGE_NAME images...${NC}"
        echo "$OLD_IMAGES" | xargs -r docker rmi 2>/dev/null || true
        echo -e "${GREEN}✓ Old images removed${NC}"
    else
        echo -e "${GREEN}✓ No old project images${NC}"
    fi

    if [[ "$PRUNE_ALL" == true ]]; then
        BUILD_CACHE=$(docker builder du --format '{{.Size}}' 2>/dev/null | head -1)
        if [[ -n "$BUILD_CACHE" ]] && [[ "$BUILD_CACHE" != "0B" ]]; then
            echo -e "${YELLOW}→ Clearing build cache...${NC}"
            docker builder prune -f 2>/dev/null || true
            echo -e "${GREEN}✓ Build cache cleared${NC}"
        else
            echo -e "${GREEN}✓ No build cache to clear${NC}"
        fi

        echo -e "${YELLOW}→ Removing unused images...${NC}"
        docker image prune -a -f 2>/dev/null || true
        echo -e "${GREEN}✓ Unused images removed${NC}"
    fi

    echo
    echo -e "${CYAN}Current disk usage:${NC}"
    docker system df
}

if [[ "$PRUNE" == true ]] && [[ "$REBUILD" != true ]]; then
    do_prune
    exit 0
fi

case $ACTION in
    stop)
        echo -e "${CYAN}Stopping container...${NC}"
        docker compose -f "$COMPOSE_FILE" down
        echo -e "${GREEN}✓ Container stopped${NC}"
        exit 0
        ;;
    logs)
        exec docker compose -f "$COMPOSE_FILE" logs -f
        ;;
    status)
        if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            echo -e "${GREEN}● Container is running${NC}"
            docker compose -f "$COMPOSE_FILE" ps
        else
            echo -e "${YELLOW}○ Container is not running${NC}"
        fi
        exit 0
        ;;
esac

echo -e "${CYAN}╔═══════════════════════════════════╗${NC}"
echo -e "${CYAN}║   lastfm-to-ytm Docker Launcher   ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════╝${NC}"
echo

echo -e "${BLUE}[1/5]${NC} Checking Docker installation..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed!${NC}"
    echo
    echo "Install Docker using one of these methods:"
    echo "  Ubuntu/Debian: sudo apt install docker.io docker-compose-v2"
    echo "  Snap:          sudo snap install docker"
    echo "  Official:      https://docs.docker.com/get-docker/"
    exit 1
fi
echo -e "${GREEN}✓ Docker is installed${NC}"

echo -e "${BLUE}[2/5]${NC} Checking Docker daemon..."
if ! docker info &> /dev/null; then
    echo -e "${RED}✗ Docker daemon is not running!${NC}"
    echo
    echo "Start Docker with:"
    echo "  sudo systemctl start docker"
    echo
    echo "Or if you need sudo for docker commands, run this script with sudo."
    exit 1
fi
echo -e "${GREEN}✓ Docker daemon is running${NC}"

echo -e "${BLUE}[3/5]${NC} Checking required files..."

if [[ -d "$SCRIPT_DIR/.env" ]]; then
    echo -e "${YELLOW}→ Removing .env directory (Docker artifact)...${NC}"
    rm -rf "$SCRIPT_DIR/.env"
fi
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    echo -e "${YELLOW}→ Creating empty .env file for first-time setup...${NC}"
    touch "$SCRIPT_DIR/.env"
fi

if [[ -d "$SCRIPT_DIR/browser.json" ]]; then
    echo -e "${YELLOW}→ Removing browser.json directory (Docker artifact)...${NC}"
    rm -rf "$SCRIPT_DIR/browser.json"
fi
if [[ ! -f "$SCRIPT_DIR/browser.json" ]]; then
    echo -e "${YELLOW}→ Creating empty browser.json for first-time setup...${NC}"
    echo '{}' > "$SCRIPT_DIR/browser.json"
fi

if command -v git &>/dev/null && git -C "$SCRIPT_DIR" rev-parse --git-dir &>/dev/null; then
    git -C "$SCRIPT_DIR" rev-parse HEAD > "$SCRIPT_DIR/COMMIT_SHA" 2>/dev/null || echo "unknown" > "$SCRIPT_DIR/COMMIT_SHA"
else
    echo "unknown" > "$SCRIPT_DIR/COMMIT_SHA"
fi

echo -e "${GREEN}✓ Required files exist${NC}"

echo -e "${BLUE}[4/5]${NC} Checking Docker image..."

IMAGE_EXISTS=$(docker images -q "$IMAGE_NAME" 2>/dev/null)

if [[ -z "$IMAGE_EXISTS" ]] || [[ "$REBUILD" == true ]]; then
    if [[ "$REBUILD" == true ]]; then
        if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
            echo -e "${YELLOW}→ Stopping and removing old container...${NC}"
            docker compose -f "$COMPOSE_FILE" down --remove-orphans 2>/dev/null || true
        fi
    fi

    if [[ "$NO_CACHE" == true ]]; then
        echo -e "${YELLOW}→ Rebuilding image (--no-cache, full rebuild)...${NC}"
        docker compose -f "$COMPOSE_FILE" build --no-cache --pull || {
            echo -e "${RED}✗ Image build failed${NC}"
            exit 1
        }
    elif [[ "$REBUILD" == true ]]; then
        echo -e "${YELLOW}→ Rebuilding image (--rebuild flag)...${NC}"
        docker compose -f "$COMPOSE_FILE" build --pull || {
            echo -e "${RED}✗ Image build failed${NC}"
            exit 1
        }
    else
        echo -e "${YELLOW}→ Building image for the first time...${NC}"
        docker compose -f "$COMPOSE_FILE" build || {
            echo -e "${RED}✗ Image build failed${NC}"
            exit 1
        }
    fi
    echo -e "${GREEN}✓ Image built successfully${NC}"

    docker builder prune --keep-storage 1GB -f >/dev/null 2>&1 || true
else
    echo -e "${GREEN}✓ Image already exists${NC}"
    echo -e "  ${CYAN}(use --rebuild to force rebuild, --no-cache for fresh build)${NC}"
fi

echo -e "${BLUE}[5/5]${NC} Starting container..."

if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}→ Container already running, restarting...${NC}"
    docker compose -f "$COMPOSE_FILE" restart || {
        echo -e "${RED}✗ Failed to restart container${NC}"
        exit 1
    }
else
    docker compose -f "$COMPOSE_FILE" up -d || {
        echo -e "${RED}✗ Failed to start container${NC}"
        exit 1
    }
fi

echo -e "${YELLOW}→ Waiting for service to be ready...${NC}"
READY=false
for ((i=1; i<=HEALTH_TIMEOUT; i++)); do
    if curl -s --max-time 2 "http://localhost:$PORT/" > /dev/null 2>&1; then
        READY=true
        break
    fi
    printf "\r  %d/%d seconds..." "$i" "$HEALTH_TIMEOUT"
    sleep 1
done
printf "\r                              \r"  # Clear the countdown line

if [[ "$READY" != true ]]; then
    echo -e "${RED}✗ Service did not become ready within ${HEALTH_TIMEOUT}s${NC}"
    echo -e "  Check logs with: ${CYAN}./run-docker.sh --logs${NC}"
    exit 1
fi

echo
echo -e "${GREEN}╔═══════════════════════════╗${NC}"
echo -e "${GREEN}║   Started successfully!   ║${NC}"
echo -e "${GREEN}╚═══════════════════════════╝${NC}"
echo
echo -e "${CYAN}Access the dashboard at:${NC}"
echo -e "  Local:    ${GREEN}http://localhost:$PORT${NC}"

if command -v hostname &> /dev/null; then
    IP=$(hostname -I 2>/dev/null | awk '{print $1}')
    if [ -n "$IP" ]; then
        echo -e "  Network:  ${GREEN}http://$IP:$PORT${NC}"
    fi
fi

echo
echo -e "${CYAN}Useful commands:${NC}"
echo "  View logs:     ./run-docker.sh --logs"
echo "  Stop:          ./run-docker.sh --stop"
echo "  Rebuild:       ./run-docker.sh --rebuild"
echo "  Status:        ./run-docker.sh --status"
echo "  Prune:         ./run-docker.sh --prune"
echo

if [[ "$PRUNE" == true ]]; then
    echo
    do_prune
fi
