"""Status, process-tree, output watching, and waiting."""

import asyncio
import contextlib

from . import remote, tmux
from .errors import ProcessError, RemoteConnectionError


async def status(
    launcher,
    process=None,
    print_to_stdout=False,
    raise_on_unavailable=True,
):
    names = [process] if process is not None else [
        name for name in launcher.cfg if name != "context"
    ]
    configs = {
        name: launcher.process(name, level=0)
        for name in names
    }
    grouped = {}
    for name, config in configs.items():
        grouped.setdefault((config.machine, config.session), []).append(name)

    result = {}
    rows = []
    for (machine, session), group_names in grouped.items():
        config = configs[group_names[0]]
        try:
            await config.connect(announce=False)
            windows = await tmux.list_windows(config.ssh, session)
        except RemoteConnectionError as exc:
            await launcher.connection_manager.invalidate(exc.machine)
            if raise_on_unavailable:
                raise
            for name in group_names:
                entry = {
                    "dead": True,
                    "pid": "-",
                    "exitstatus": "-",
                    "run_pending": False,
                    "kill_pending": False,
                    "state": "UNAVAILABLE",
                    "machine": machine or "local",
                    "error": str(exc),
                }
                result.setdefault(session, {})[name] = entry
                rows.append(_row(name, session, entry))
            continue

        for name in group_names:
            entry = dict(windows.get(name, {}))
            if not entry:
                entry = {
                    "dead": True,
                    "pid": "-",
                    "exitstatus": "-",
                    "run_pending": False,
                    "kill_pending": False,
                }
                state = "STOPPED"
            elif entry.get("run_pending"):
                state = "STARTING"
            elif entry.get("kill_pending"):
                state = "STOPPING"
            elif entry.get("dead"):
                state = "DEAD"
            else:
                state = "RUNNING"
            entry["state"] = state
            entry["machine"] = machine or "local"
            result.setdefault(session, {})[name] = entry
            rows.append(_row(name, session, entry))

    if print_to_stdout:
        launcher.reporter.status_table(rows)
    return result


def _row(process, session, entry):
    return {
        "process": process,
        "session": session,
        "machine": entry.get("machine", "local"),
        "state": entry.get("state", "UNKNOWN"),
        "pid": entry.get("pid", "-"),
        "exitstatus": entry.get("exitstatus", "-"),
    }


async def pstree(launcher, process=None):
    names = [process] if process is not None else [
        name for name in launcher.cfg if name != "context"
    ]
    result = {}
    for name in names:
        config = launcher.process(name, level=0)
        try:
            await config.connect(announce=False)
            windows = await tmux.list_windows(config.ssh, config.session)
            info = windows.get(name)
            if not info or info.get("dead"):
                continue
            _, stdout, _ = await remote.run_cmd(
                config.ssh,
                "python3 /tmp/concert_launcher_print_ps_tree.py {}".format(
                    info["pid"]
                ),
            )
            result[name] = stdout
            await config.print("process tree:\n  {}".format(stdout.replace("\n", "\n  ")))
        except RemoteConnectionError as exc:
            await launcher.connection_manager.invalidate(exc.machine)
            raise
    return result


class Printer:
    def __init__(self, process):
        self.process = process

    async def print(self, line):
        print("[{}] {}".format(self.process, line), end="")


def default_get_printer(process):
    return Printer(process).print


async def watch(
    launcher,
    process=None,
    printer_coro_factory=default_get_printer,
    num_lines="+1",
):
    names = [process] if process is not None else [
        name for name in launcher.cfg if name != "context"
    ]
    tasks = []
    for name in names:
        config = launcher.process(name, level=0)
        try:
            await config.connect(announce=False)
        except RemoteConnectionError as exc:
            await launcher.connection_manager.invalidate(exc.machine)
            raise
        command = "touch /tmp/{0}.stdout && tail -f -n {1} /tmp/{0}.stdout".format(
            name, num_lines
        )
        tasks.append(
            remote.watch_process(
                config.ssh,
                command,
                stdout_coro=printer_coro_factory(name),
            )
        )
    try:
        await asyncio.gather(*tasks)
    except RemoteConnectionError as exc:
        await launcher.connection_manager.invalidate(exc.machine)
        raise


async def wait_process(launcher, process, timeout=0, watch_output=True):
    config = launcher.process(process, level=0)
    try:
        await config.connect(announce=False)
    except RemoteConnectionError as exc:
        await launcher.connection_manager.invalidate(exc.machine)
        raise

    watch_task = None
    if watch_output:
        watch_task = asyncio.ensure_future(
            watch(launcher, process, num_lines="0")
        )

    async def poll():
        while True:
            windows = await tmux.list_windows(config.ssh, config.session)
            info = windows.get(process)
            if info is None:
                raise ProcessError("process {!r} is not running".format(process))
            if info["dead"]:
                return info["exitstatus"]
            await asyncio.sleep(1)

    try:
        if timeout and timeout > 0:
            return await asyncio.wait_for(poll(), timeout=timeout)
        return await poll()
    except RemoteConnectionError as exc:
        await launcher.connection_manager.invalidate(exc.machine)
        raise
    finally:
        if watch_task is not None:
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await watch_task
