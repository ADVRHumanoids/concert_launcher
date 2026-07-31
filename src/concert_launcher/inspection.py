"""Inspect managed processes through status, trees, output, and exit waits.

All operations enforce tmux ownership before observing or following a named
window. Remote failures invalidate cached connections so callers can recover
without accidentally reusing a broken transport.
"""

import asyncio
import contextlib
import shlex

from . import remote, tmux
from .errors import ProcessError, RemoteConnectionError


async def status(
    launcher,
    process=None,
    print_to_stdout=False,
    raise_on_unavailable=True,
):
    """Return normalized lifecycle state for configured processes."""
    names = [process] if process is not None else [
        name for name in launcher.cfg if name != "context"
    ]

    # Build each process view once, then group by transport and tmux session so
    # one SSH/tmux query can serve every process in that group.
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
            # Dashboard mode keeps other hosts visible; strict library mode
            # re-raises the typed error after removing the stale connection.
            await launcher.connection_manager.invalidate(exc.machine)
            if raise_on_unavailable:
                raise
            for name in group_names:
                entry = {
                    "dead": True,
                    "pid": "-",
                    "exitstatus": "-",
                    "managed": False,
                    "legacy_managed": False,
                    "ambiguous": False,
                    "run_pending": False,
                    "kill_pending": False,
                    "state": "UNAVAILABLE",
                    "machine": machine or "local",
                    "error": str(exc),
                }
                result.setdefault(session, {})[name] = entry
                rows.append(_row(name, session, entry))
            continue

        # Convert raw tmux facts into the public launcher states. Foreign or
        # ambiguous name collisions are surfaced as CONFLICT, never RUNNING.
        for name in group_names:
            entry = dict(windows.get(name, {}))
            if not entry:
                entry = {
                    "dead": True,
                    "pid": "-",
                    "exitstatus": "-",
                    "managed": False,
                    "legacy_managed": False,
                    "ambiguous": False,
                    "run_pending": False,
                    "kill_pending": False,
                }
                state = "STOPPED"
            else:
                conflict = tmux.window_conflict_message(session, name, entry)
                if conflict is not None:
                    state = "CONFLICT"
                    entry["error"] = conflict
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
    """Project a detailed status entry into one terminal-table row."""
    return {
        "process": process,
        "session": session,
        "machine": entry.get("machine", "local"),
        "state": entry.get("state", "UNKNOWN"),
        "pid": entry.get("pid", "-"),
        "exitstatus": entry.get("exitstatus", "-"),
    }


async def pstree(launcher, process=None):
    """Return process trees for live, launcher-managed tmux windows."""
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
            if not info:
                continue
            tmux.require_managed_window(config.session, name, info)
            if info.get("dead"):
                continue

            # The target-side helper walks descendants from the pane PID and
            # returns text suitable for both APIs and terminal output.
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
    """Default line printer used when a library caller supplies no callback."""

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
    """Follow output files for one or all configured processes."""
    names = [process] if process is not None else [
        name for name in launcher.cfg if name != "context"
    ]
    tasks = []
    for name in names:
        config = launcher.process(name, level=0)
        try:
            await config.connect(announce=False)
            windows = await tmux.list_windows(config.ssh, config.session)
            info = windows.get(name)
            if info is not None:
                tmux.require_managed_window(config.session, name, info)
        except RemoteConnectionError as exc:
            await launcher.connection_manager.invalidate(exc.machine)
            raise

        # Each process gets one independent ``tail -f`` stream. Quoting keeps
        # process names and caller-provided tail positions shell-safe.
        output_path = shlex.quote("/tmp/{}.stdout".format(name))
        tail_position = shlex.quote(str(num_lines))
        command = "touch {path} && tail -f -n {lines} {path}".format(
            path=output_path,
            lines=tail_position,
        )
        tasks.append(
            remote.watch_process(
                config.ssh,
                command,
                stdout_coro=printer_coro_factory(name),
            )
        )
    try:
        # A failure in any stream ends the combined watch and exposes the
        # affected machine through RemoteConnectionError.
        await asyncio.gather(*tasks)
    except RemoteConnectionError as exc:
        await launcher.connection_manager.invalidate(exc.machine)
        raise


async def wait_process(launcher, process, timeout=0, watch_output=True):
    """Wait for one managed tmux window and return its real exit status."""
    config = launcher.process(process, level=0)
    try:
        # Validate ownership before starting an optional watch task, preventing
        # output operations from attaching to a foreign same-name window.
        await config.connect(announce=False)
        initial_windows = await tmux.list_windows(config.ssh, config.session)
        initial_info = initial_windows.get(process)
        if initial_info is not None:
            tmux.require_managed_window(config.session, process, initial_info)
    except RemoteConnectionError as exc:
        await launcher.connection_manager.invalidate(exc.machine)
        raise

    watch_task = None
    if watch_output:
        watch_task = asyncio.ensure_future(
            watch(launcher, process, num_lines="0")
        )

    async def poll():
        # Tmux may briefly report a dead pane before populating its exit status,
        # so that state is polled at a shorter interval until complete.
        while True:
            windows = await tmux.list_windows(config.ssh, config.session)
            info = windows.get(process)
            if info is None:
                raise ProcessError("process {!r} is not running".format(process))
            tmux.require_managed_window(config.session, process, info)
            if info["dead"]:
                if info["exitstatus"] is None:
                    await asyncio.sleep(0.05)
                    continue
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
        # Watching is ancillary to waiting. Always cancel it without masking the
        # process result or the exception raised by the polling path.
        if watch_task is not None:
            watch_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await watch_task
