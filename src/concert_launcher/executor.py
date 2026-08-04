"""Backward-compatible function API.

New integrations should instantiate :class:`concert_launcher.Launcher` so SSH
recovery and connection lifetime are explicit.
"""

from .connections import default_connection_manager
from .inspection import Printer, default_get_printer
from .launcher import Launcher
from .process import ConfigParser, Variant


async def execute_process(
    process,
    cfg,
    params=None,
    variants=None,
    notify_event=None,
    level=0,
):
    del level
    return await Launcher(cfg, connection_manager=default_connection_manager).execute_process(
        process,
        params=params,
        variants=variants,
        notify_event=notify_event,
    )


async def kill(process, cfg, level=0, graceful=True, notify_event=None):
    del level
    return await Launcher(cfg, connection_manager=default_connection_manager).kill(
        process=process,
        graceful=graceful,
        notify_event=notify_event,
    )


async def status(process, cfg, print_to_stdout=True):
    return await Launcher(cfg, connection_manager=default_connection_manager).status(
        process=process,
        print_to_stdout=print_to_stdout,
        raise_on_unavailable=False,
    )


async def pstree(process, cfg, level=0):
    del level
    return await Launcher(cfg, connection_manager=default_connection_manager).pstree(process=process)


async def watch(
    process,
    cfg,
    printer_coro_factory=default_get_printer,
    num_lines="+1",
):
    return await Launcher(cfg, connection_manager=default_connection_manager).watch(
        process=process,
        printer_coro_factory=printer_coro_factory,
        num_lines=num_lines,
    )


async def wait_process(process, cfg, timeout=0):
    return await Launcher(cfg, connection_manager=default_connection_manager).wait_process(process=process, timeout=timeout)
