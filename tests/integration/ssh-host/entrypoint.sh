#!/bin/bash
set -euo pipefail

PUBLIC_KEY=/test-keys/id_ed25519.pub
AUTHORIZED_KEYS=/home/tester/.ssh/authorized_keys

if [[ ! -s "$PUBLIC_KEY" ]]; then
    echo "missing integration-test public key: $PUBLIC_KEY" >&2
    exit 1
fi

install -o tester -g tester -m 600 "$PUBLIC_KEY" "$AUTHORIZED_KEYS"
ssh-keygen -A

exec /usr/sbin/sshd -D -e \
    -o PasswordAuthentication=no \
    -o KbdInteractiveAuthentication=no \
    -o PubkeyAuthentication=yes \
    -o PermitRootLogin=no
