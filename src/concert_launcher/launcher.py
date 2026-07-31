"""High-level asyncio API for Concert Launcher."""

import asyncio

from .connections import ConnectionManager
from .errors import ConfigurationError, RemoteConnectionError
from .inspection import default_get_printer, pstree, status, wait_process, watch
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

    async def watch_with_recovery(
        self,
        process,
        printer_coro_factory=None,
        num_lines="+1",
        retries=1,
        retry_delay=1.0,
    ):
        """Watch one process and resume after retryable SSH interruptions.

        When ``num_lines`` is an absolute tail position such as ``"+1"``,
        retries resume at the first line not yet delivered. Other tail modes
        are restarted unchanged after reconnecting.
        """
        if process is None:
            raise ConfigurationError(
                "watch_with_recovery requires an explicit process name"
            )

        output_factory = printer_coro_factory or default_get_printer
        output_printer = output_factory(process)
        delivered = 0
        attempt = 0
        current_num_lines = num_lines

        def counting_factory(name):
            if name != process:
                raise ConfigurationError(
                    "unexpected process {!r} while watching {!r}".format(
                        name, process
                    )
                )

            async def print_line(line):
                nonlocal delivered
                await output_printer(line)
                delivered += 1

            return print_line

        while True:
            try:
                result = await self.watch(
                    process,
                    printer_coro_factory=counting_factory,
                    num_lines=current_num_lines,
                )
            except RemoteConnectionError as exc:
                if attempt >= retries:
                    raise
                recovery_target = exc
            else:
                recovery_target = (self.cfg.get(process) or {}).get("machine")
                if recovery_target in (None, "local") or attempt >= retries:
                    return result

            attempt += 1
            await self.recover(recovery_target, reconnect=False)
            current_num_lines = _resume_tail_position(num_lines, delivered)
            if retry_delay:
                await asyncio.sleep(retry_delay)

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


def _resume_tail_position(num_lines, delivered):
    if isinstance(num_lines, str) and num_lines.startswith("+"):
        try:
            first_line = int(num_lines[1:])
        except ValueError:
            return num_lines
        return "+{}".format(first_line + delivered)
    return num_lines
