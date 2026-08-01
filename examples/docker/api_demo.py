#!/usr/bin/env python3
"""Run the same distributed graph through the ANSI-free asyncio API."""

import asyncio
import contextlib
from pathlib import Path

import yaml

from concert_launcher import Launcher


CONFIG_PATH = Path(__file__).with_name("launcher.yaml")


async def collect_lines(launcher, process, count=3):
    """Collect a bounded sample from the otherwise unbounded watch API."""
    lines = []
    complete = asyncio.Event()

    def printer_factory(name):
        async def print_line(line):
            lines.append(line.rstrip())
            print("{}: {}".format(name, line), end="")
            if len(lines) >= count:
                complete.set()

        return print_line

    task = asyncio.create_task(
        launcher.watch(
            process,
            printer_coro_factory=printer_factory,
            num_lines="+1",
        )
    )
    try:
        await asyncio.wait_for(complete.wait(), timeout=5)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    return lines


async def main():
    with CONFIG_PATH.open() as stream:
        config = yaml.safe_load(stream)

    # Launcher is plain-text by default. ANSI styling is a CLI concern.
    launcher = Launcher(config)

    async def on_event(process, message):
        print("event {}: {}".format(process, message))

    try:
        await launcher.execute_process("heartbeat_a", notify_event=on_event)
        await launcher.execute_process("heartbeat_b", notify_event=on_event)

        # Starting the one-shot probe automatically starts and waits for web.
        success = await launcher.execute_process(
            "http_probe",
            variants=["verbose"],
            params={"probe_message": "api-probe-ready"},
            notify_event=on_event,
        )
        if not success:
            raise RuntimeError("http_probe failed")

        # API status is structured data unless print_to_stdout=True is requested.
        status = await launcher.status(print_to_stdout=False)
        for process in ("web", "heartbeat_a", "heartbeat_b", "http_probe"):
            print("state {}: {}".format(
                process,
                status["concert_examples"][process]["state"],
            ))

        lines = await collect_lines(launcher, "heartbeat_a")
        print("collected lines: {}".format(lines))
    finally:
        with contextlib.suppress(Exception):
            await launcher.kill()
        await launcher.close()


if __name__ == "__main__":
    asyncio.run(main())
