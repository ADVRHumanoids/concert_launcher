#!/bin/bash

NAME=$1
CMD=$2

STDOUT_FILE=/tmp/$NAME.stdout

echo "starting process $NAME ($CMD)" >> $STDOUT_FILE

export PYTHONUNBUFFERED=1

script --append --flush --return --command "bash -ic \"$CMD\"" $STDOUT_FILE

echo "process exited with code $?" >> $STDOUT_FILE

sleep 1