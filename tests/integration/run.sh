#!/bin/bash
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
STATE_DIR="$HERE/.state"
COMPOSE=(docker compose -f "$HERE/docker-compose.yml")

for command in docker ssh-keygen; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "required command not found: $command" >&2
        exit 1
    fi
done
docker compose version >/dev/null

cleanup() {
    "${COMPOSE[@]}" down --volumes --remove-orphans >/dev/null 2>&1 || true
    rm -rf "$STATE_DIR"
}
trap cleanup EXIT

rm -rf "$STATE_DIR"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
ssh-keygen -q -t ed25519 -N '' -f "$STATE_DIR/id_ed25519"
chmod 600 "$STATE_DIR/id_ed25519"

"${COMPOSE[@]}" build
"${COMPOSE[@]}" run --rm runner "$@"
