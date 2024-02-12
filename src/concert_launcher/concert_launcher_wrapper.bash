#!/bin/bash

NAME=$1
CMD=$2

STDOUT_FILE=/tmp/$NAME.stdout
STDERR_FILE=/tmp/$NAME.stderr

echo "starting process $NAME ($CMD)" >> $STDOUT_FILE
echo "starting process $NAME ($CMD)" >> $STDERR_FILE

export PYTHONUNBUFFERED=1

bash -ic "$CMD" 1> >(tee -a $STDOUT_FILE) 2> >(tee -a $STDERR_FILE >&2)

echo "process exited with code $?" >> $STDOUT_FILE
echo "process exited with code $?" >> $STDERR_FILE

sleep 1