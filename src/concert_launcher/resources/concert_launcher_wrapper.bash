#!/bin/bash
set -u
set -o pipefail

NAME=$1
CMD=$2
STDOUT_FILE=/tmp/$NAME.stdout

cleanup() {
    rm -f "/tmp/$NAME.STARTING" "/tmp/$NAME.KILLING"
}
trap cleanup EXIT

# The wrapper shares tmux's terminal with the launched command. Ignore the
# stop signals here so the foreground command can handle them and the wrapper
# can still record its exit status and clean up marker files.
trap ':' INT QUIT

echo "starting process $NAME ($CMD)" | tee -a "$STDOUT_FILE"

export PYTHONUNBUFFERED=1

if command -v ts >/dev/null 2>&1; then
    stdbuf -oL -eL bash -ic "$CMD" 2>&1 \
        | stdbuf -oL -eL ts '[%H:%M:%.S]' \
        | stdbuf -oL -eL tee -a "$STDOUT_FILE"
    RET=${PIPESTATUS[0]}
else
    stdbuf -oL -eL bash -ic "$CMD" 2>&1 \
        | stdbuf -oL -eL tee -a "$STDOUT_FILE"
    RET=${PIPESTATUS[0]}
fi

echo "process exited with code $RET" | tee -a "$STDOUT_FILE"
sleep 1
exit "$RET"
