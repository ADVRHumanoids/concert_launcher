#!/bin/bash
# Build an isolated two-host lab, run one example, and clean up all resources.
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
trap cleanup EXIT INT TERM

rm -rf "$STATE_DIR"
mkdir -p "$STATE_DIR"
chmod 700 "$STATE_DIR"
ssh-keygen -q -t ed25519 -N '' -f "$STATE_DIR/id_ed25519"
chmod 600 "$STATE_DIR/id_ed25519"

case "${1:-shell}" in
    cli)
        command=(bash ./cli_demo.sh)
        ;;
    api)
        command=(python3 ./api_demo.py)
        ;;
    recovery)
        command=(python3 ./recovery_demo.py)
        ;;
    shell)
        command=(bash)
        ;;
    *)
        command=("$@")
        ;;
esac

"${COMPOSE[@]}" build
"${COMPOSE[@]}" run --rm runner "${command[@]}"
