#!/bin/bash
# Prepare the Docker lab and leave it running for interactive CLI use.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
STATE_DIR="$HERE/.state"
COMPOSE=(docker compose -f "$HERE/docker-compose.yml")

for command in docker ssh-keygen ssh-keyscan; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "required command not found: $command" >&2
        exit 1
    fi
done
docker compose version >/dev/null

generated_keys=0
if [[ ! -s "$STATE_DIR/id_ed25519" || ! -s "$STATE_DIR/id_ed25519.pub" ]]; then
    rm -rf "$STATE_DIR"
    mkdir -p "$STATE_DIR"
    chmod 700 "$STATE_DIR"
    ssh-keygen -q -t ed25519 -N '' -f "$STATE_DIR/id_ed25519"
    chmod 600 "$STATE_DIR/id_ed25519"
    generated_keys=1
fi

"${COMPOSE[@]}" build

up_args=(up -d)
if [[ "$generated_keys" == 1 ]]; then
    up_args+=(--force-recreate)
fi
up_args+=(ssh-proxy-a ssh-proxy-b)
"${COMPOSE[@]}" "${up_args[@]}"

# Run the runner entrypoint once so key installation and SSH host discovery are
# verified before the user opens an interactive shell.
"${COMPOSE[@]}" run --rm runner true

KNOWN_HOSTS="$STATE_DIR/known_hosts"
: > "$KNOWN_HOSTS"
for port in 2222 2223; do
    for attempt in $(seq 1 30); do
        if ssh-keyscan -T 1 -p "$port" 127.0.0.1 >> "$KNOWN_HOSTS" 2>/dev/null; then
            break
        fi
        if [[ "$attempt" == 30 ]]; then
            echo "SSH proxy on localhost:$port did not become reachable" >&2
            exit 1
        fi
        sleep 0.2
    done
done
chmod 600 "$KNOWN_HOSTS"

HOST_ENV="$STATE_DIR/host-env"
{
    printf 'export CONCERT_LAUNCHER_SSH_KEY=%q\n' "$STATE_DIR/id_ed25519"
    printf 'export CONCERT_LAUNCHER_KNOWN_HOSTS=%q\n' "$KNOWN_HOSTS"
    printf 'export CONCERT_LAUNCHER_DEFAULT_CONFIG=%q\n' "$HERE/launcher-host.yaml"
    printf 'export CONCERT_TEST_SSH_A=%q\n' "tester@127.0.0.1:2222"
    printf 'export CONCERT_TEST_SSH_B=%q\n' "tester@127.0.0.1:2223"
    printf 'export CONCERT_TEST_PROXY_A=%q\n' "http://127.0.0.1:8474"
    printf 'export CONCERT_TEST_PROXY_B=%q\n' "http://127.0.0.1:8475"
} > "$HOST_ENV"
chmod 600 "$HOST_ENV"

cat <<EOF

Docker example lab is ready.

Try an interactive runner shell:
  docker compose -f examples/docker/docker-compose.yml run --rm runner bash

From inside that shell:
  concert_launcher run heartbeat_a
  concert_launcher run heartbeat_b
  concert_launcher run http_probe --variants verbose
  concert_launcher status
  concert_launcher watch --num-lines +1
  tail -f -s 0.1 /tmp/heartbeat_a.stdout
  concert_launcher kill --all

Or run one command directly from the host:
  docker compose -f examples/docker/docker-compose.yml run --rm runner concert_launcher status

Use the lab from this host:
  source examples/docker/.state/host-env
  concert_launcher status
  concert_launcher run heartbeat_a
  concert_launcher watch heartbeat_a
  concert_launcher kill --all

Host endpoints:
  ssh-a proxy: 127.0.0.1:2222
  ssh-b proxy: 127.0.0.1:2223
  proxy-a control: http://127.0.0.1:8474
  proxy-b control: http://127.0.0.1:8475

When you are done:
  docker compose -f examples/docker/docker-compose.yml down --volumes --remove-orphans
  rm -rf examples/docker/.state

Repository:
  $ROOT
EOF
