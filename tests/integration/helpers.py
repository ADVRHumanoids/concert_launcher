"""Helpers shared by Docker-backed SSH integration tests."""

import asyncio
import os
import shlex
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


def machine(name="A"):
    return os.environ[f"CONCERT_TEST_SSH_{name.upper()}"]


def unique_name(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


async def wait_for_queue(queue, predicate, timeout=10.0):
    async def receive():
        while True:
            item = await queue.get()
            if predicate(item):
                return item

    return await asyncio.wait_for(receive(), timeout=timeout)


async def cancel_task(task):
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
