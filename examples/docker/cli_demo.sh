#!/bin/bash
# Walk through the public CLI against two real SSH/tmux hosts.
set -euo pipefail

cleanup() {
    concert_launcher kill --all >/dev/null 2>&1 || true
}
trap cleanup EXIT

step() {
    printf '\n=== %s ===\n' "$1"
}

step "Start persistent processes on both SSH hosts"
concert_launcher run heartbeat_a
concert_launcher run heartbeat_b

step "Start a cross-host dependency graph and select a variant"
concert_launcher run http_probe --variants verbose

step "Inspect all configured processes"
concert_launcher status

step "Watch both heartbeat streams; each process label has a stable color"
set +e
timeout 2s concert_launcher watch --num-lines +1
watch_status=$?
set -e
if [[ "$watch_status" != 0 && "$watch_status" != 124 ]]; then
    exit "$watch_status"
fi

step "Refresh the colored status table for two seconds"
set +e
timeout 2s concert_launcher status --watch
status_watch_status=$?
set -e
if [[ "$status_watch_status" != 0 && "$status_watch_status" != 124 ]]; then
    exit "$status_watch_status"
fi

step "Stop every managed process"
concert_launcher kill --all
