"""High-level asyncio API for Concert Launcher."""

import asyncio

from .connections import ConnectionManager
from .errors import RemoteConnectionError
from .inspection import pstree, status, wait_process, watch
from .lifecycle import execute_process, kill
from .output import ConsoleReporter
from .process import ConfigParser


class Launcher:
    """Reusable, library-friendly process launcher.

    SSH failures are raised as :class:`RemoteConnectionError`. The exception
    exposes the affected machine and can be passed to :meth:`recover` before
    retrying an operation.
    """

    def __init__(self, cfg, connection_manager=None, reporter=None):
        self.cfg = cfg
        self.connection_manager = connection_manager or ConnectionManager()
        self.reporter = reporter or ConsoleReporter()

    def process(self, name, level=0, notify_event=None):
        return ConfigParser(
            name,
            self.cfg,
            notify_ev_callback=notify_event,
            level=level,
            connection_manager=self.connection_manager,
            reporter=self.reporter,
        )

    async def execute_process(
        self,
        process,
        params=None,
        variants=None,
        notify_event=None,
    ):
        return await execute_process(
            self,
            process,
            params=params,
            variants=variants,
            notify_event=notify_event,
        )

    async def execute_with_recovery(
        self,
        process,
        params=None,
        variants=None,
        notify_event=None,
        retries=1,
        retry_delay=1.0,
    ):
        """Execute and reconnect automatically after retryable SSH failures."""
        attempt = 0
        while True:
            try:
                return await self.execute_process(
                    process,
                    params=params,
                    variants=variants,
                    notify_event=notify_event,
                )
            except RemoteConnectionError as exc:
                if attempt >= retries:
                    raise
                attempt += 1
                await self.recover(exc, reconnect=False)
                if retry_delay:
                    await asyncio.sleep(retry_delay)

    async def kill(self, process=None, graceful=True, notify_event=None):
        return await kill(
            self,
            process=process,
            graceful=graceful,
            notify_event=notify_event,
        )

    async def status(
        self,
        process=None,
        print_to_stdout=False,
        raise_on_unavailable=True,
    ):
        return await status(
            self,
            process=process,
            print_to_stdout=print_to_stdout,
            raise_on_unavailable=raise_on_unavailable,
        )

    async def pstree(self, process=None):
        return await pstree(self, process=process)

    async def watch(
        self,
        process=None,
        printer_coro_factory=None,
        num_lines="+1",
    ):
        kwargs = {"num_lines": num_lines}
        if printer_coro_factory is not None:
            kwargs["printer_coro_factory"] = printer_coro_factory
        return await watch(self, process=process, **kwargs)

    async def wait_process(self, process, timeout=0, watch_output=True):
        return await wait_process(
            self,
            process,
            timeout=timeout,
            watch_output=watch_output,
        )

    async def recover(self, error_or_machine, reconnect=True):
        """Invalidate a broken SSH connection and optionally reconnect now."""
        machine = (
            error_or_machine.machine
            if isinstance(error_or_machine, RemoteConnectionError)
            else error_or_machine
        )
        await self.connection_manager.invalidate(machine)
        if reconnect:
            return await self.connection_manager.get(machine)
        return None

    async def close(self):
        await self.connection_manager.close_all()
