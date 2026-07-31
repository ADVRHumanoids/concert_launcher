#!/usr/bin/env python3
"""Foreground process used to verify delivery of SIGINT through tmux."""

from pathlib import Path
import signal
import sys


signal_path = Path(sys.argv[1])
ready_path = Path(sys.argv[2])


def handle_sigint(_signum, _frame):
    signal_path.write_text("SIGINT", encoding="ascii")
    raise SystemExit(0)


signal.signal(signal.SIGINT, handle_sigint)
ready_path.write_text("ready", encoding="ascii")
print("signal-handler-ready", flush=True)
signal.pause()
