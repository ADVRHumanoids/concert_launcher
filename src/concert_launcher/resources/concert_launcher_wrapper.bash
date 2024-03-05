#!/bin/bash

NAME=$1
CMD=$2

if ! command -v ts &> /dev/null
then
    echo "ts could not be found"
else
    CMD="$CMD | ts '[%Y-%m-%d %H:%M:%.S]'"
fi

STDOUT_FILE=/tmp/$NAME.stdout

echo "starting process $NAME ($CMD)" >> $STDOUT_FILE

export PYTHONUNBUFFERED=1

script --append --flush --return --command "bash -ic \"$CMD\"" $STDOUT_FILE

RET=$?

echo "process exited with code $RET" >> $STDOUT_FILE

sleep 1

exit $RET