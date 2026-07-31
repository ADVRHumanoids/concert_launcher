"""Helpers shared by Docker-backed SSH integration tests."""

import asyncio
import json
import os
import shlex
import urllib.request
import uuid

import asyncssh


class RemoteHost:
    def __init__(self, machine):
        self.machine = machine
        self.user, self.host = machine.split("@", 1)
        self.connection = None

    async def connect(self):
        self.connection = await asyncssh.connect(
            self.host,
            username=self.user,
        )
        return self

    async def close(self):
        if self.connection is None:
            return
        self.connection.close()
        await self.connection.wait_closed()
        self.connection = None

    async def run(self, command, check=True):
        result = await self.connection.run(command, check=check)
        return result.stdout.strip()

    async def cleanup(self, session, process_names):
        quoted_session = shlex.quote(session)
        files = " ".join(
            shlex.quote(f"/tmp/{name}{suffix}")
            for name in process_names
            for suffix in (".stdout", ".STARTING", ".KILLING")
        )
        await self.run(
            f"tmux kill-session -t {quoted_session} >/dev/null 2>&1 || true; "
            f"rm -f {files}",
            check=False,
        )


class SSHProxy:
    def __init__(self, url):
        self.url = url.rstrip("/")

    async def enable(self):
        return await self._request("/enable")

    async def disable(self):
        return await self._request("/disable")

    async def status(self):
        return await self._request("/status")

    async def _request(self, path):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._request_sync, path)

    def _request_sync(self, path):
        request = urllib.request.Request(
            self.url + path,
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))


def machine(name="A"):
    return os.environ[f"CONCERT_TEST_SSH_{name.upper()}"]


def direct_machine(name="A"):
    return os.environ[f"CONCERT_TEST_DIRECT_SSH_{name.upper()}"]


def proxy_url(name="A"):
    return os.environ[f"CONCERT_TEST_PROXY_{name.upper()}"]


def unique_name(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def unique_port():
    return 40000 + (uuid.uuid4().int % 20000)


async def wait_for_queue(queue, predicate, timeout=10.0):
    async def receive():
        while True:
            item = await queue.get()
            if predicate(item):
                return item

    return await asyncio.wait_for(receive(), timeout=timeout)


async def wait_until(predicate, timeout=10.0, interval=0.1):
    async def poll():
        while True:
            result = await predicate()
            if result:
                return result
            await asyncio.sleep(interval)

    return await asyncio.wait_for(poll(), timeout=timeout)


async def cancel_task(task):
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
