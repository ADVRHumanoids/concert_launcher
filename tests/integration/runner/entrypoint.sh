#!/bin/bash
set -euo pipefail

mkdir -p /root/.ssh
chmod 700 /root/.ssh
install -m 600 /test-keys/id_ed25519 /root/.ssh/id_ed25519

: > /root/.ssh/known_hosts
for host in ssh-a ssh-b ssh-proxy-a ssh-proxy-b; do
    for attempt in $(seq 1 30); do
        if ssh-keyscan -T 1 "$host" >> /root/.ssh/known_hosts 2>/dev/null; then
            break
        fi
        if [[ "$attempt" == 30 ]]; then
            echo "SSH host $host did not become ready" >&2
            exit 1
        fi
        sleep 0.2
    done
done
chmod 600 /root/.ssh/known_hosts

exec "$@"
