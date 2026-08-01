#!/usr/bin/env python3
"""Show explicit API recovery while the remote tmux process keeps running."""

import asyncio
import contextlib
import json
import os
import urllib.request
from pathlib import Path

import yaml

from concert_launcher import Launcher, RemoteConnectionError


CONFIG_PATH = Path(__file__).with_name("launcher.yaml")
PROXY_URL = os.environ.get("CONCERT_TEST_PROXY_A", "http://ssh-proxy-a:8474")
MACHINE = "tester@ssh-proxy-a"


def set_proxy(path):
    request = urllib.request.Request(PROXY_URL + path, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


async def main():
    with CONFIG_PATH.open() as stream:
        config = yaml.safe_load(stream)

    launcher = Launcher(config)
    try:
        await launcher.execute_process("heartbeat_a")
        await asyncio.sleep(0.6)
        before = await launcher.status("heartbeat_a")
        print("before outage:", before["concert_examples"]["heartbeat_a"]["state"])

        # The control port stays available while the proxy drops active SSH
        # tunnels. Tmux and heartbeat_a continue running on ssh-a.
        print("disable proxy:", await asyncio.to_thread(set_proxy, "/disable"))

        try:
            await launcher.status("heartbeat_a")
        except RemoteConnectionError as error:
            print("caught typed failure for:", error.machine)
            print("enable proxy:", await asyncio.to_thread(set_proxy, "/enable"))
            await launcher.recover(error)
        else:
            raise RuntimeError("expected the disabled proxy to break SSH")

        after = await launcher.status("heartbeat_a")
        print("after recovery:", after["concert_examples"]["heartbeat_a"]["state"])
    finally:
        await asyncio.to_thread(set_proxy, "/enable")
        await launcher.recover(MACHINE, reconnect=False)
        with contextlib.suppress(Exception):
            await launcher.kill("heartbeat_a")
        await launcher.close()


if __name__ == "__main__":
    asyncio.run(main())
