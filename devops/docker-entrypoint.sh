#!/bin/bash
set -e

HOST_UID=$(stat -c '%u' /app/config 2>/dev/null || echo 1000)
HOST_GID=$(stat -c '%g' /app/config 2>/dev/null || echo 1000)

if [ "$HOST_UID" != "0" ]; then
    usermod -u "$HOST_UID" lastfm 2>/dev/null || true
    groupmod -g "$HOST_GID" lastfm 2>/dev/null || true
fi

chmod -R 775 /app/cache /app/config 2>/dev/null || true

chown -R lastfm:lastfm /app/cache /app/config 2>/dev/null || true

gosu lastfm test -f /app/config/search_overrides.json || \
    gosu lastfm sh -c 'echo "{\"_overrides\": {}, \"_blacklist\": {}}" > /app/config/search_overrides.json'

[ -d /app/.env ] && rm -rf /app/.env
[ -f /app/.env ] || touch /app/.env
chown lastfm:lastfm /app/.env 2>/dev/null || true

exec gosu lastfm "$@"
