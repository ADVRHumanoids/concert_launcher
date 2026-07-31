#!/bin/bash
set -u

NAME=$1
CMD=$2
STDOUT_FILE=/tmp/$NAME.stdout
RUNNER_FILE=/tmp/$NAME.runner.$$.bash

cleanup() {
    rm -f "$RUNNER_FILE"
    rm -f "/tmp/$NAME.STARTING" "/tmp/$NAME.KILLING"
}
trap cleanup EXIT

{
    echo '#!/bin/bash'
    echo 'set -o pipefail'
    echo 'export PYTHONUNBUFFERED=1'
    printf 'CMD=%q\n' "$CMD"
    cat <<'RUNNER'
if command -v ts >/dev/null 2>&1; then
    stdbuf -oL bash -ic "$CMD" 2>&1 | ts '[%H:%M:%.S]'
else
    stdbuf -oL bash -ic "$CMD"
fi
RUNNER
} > "$RUNNER_FILE"
chmod 700 "$RUNNER_FILE"

echo "starting process $NAME ($CMD)" >> "$STDOUT_FILE"

script --append --flush --return --command "$RUNNER_FILE" "$STDOUT_FILE"
RET=$?

echo "process exited with code $RET" >> "$STDOUT_FILE"
sleep 1
exit "$RET"
