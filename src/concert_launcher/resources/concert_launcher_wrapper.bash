#!/bin/bash

NAME=$1
CMD=$2

STDOUT_FILE=/tmp/$NAME.stdout

echo "starting process $NAME ($CMD)" >> $STDOUT_FILE

export PYTHONUNBUFFERED=1

script --append --flush --return --command "bash -ic \"$CMD\"" $STDOUT_FILE

RET=$?

echo "process exited with code $RET" >> $STDOUT_FILE

sleep 1

exit $RET