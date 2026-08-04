#!/usr/bin/env python3
"""Foreground process which emits deterministic output until stopped."""

import itertools
import signal
import time


running = True


def stop(*_args):
    global running
    running = False


signal.signal(signal.SIGINT, stop)
signal.signal(signal.SIGTERM, stop)

for counter in itertools.count(1):
    if not running:
        break
    print("tick-{}".format(counter), flush=True)
    time.sleep(0.2)
