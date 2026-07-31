"""Tmux process-management primitives."""

import asyncio
import logging
import shlex

from .errors import CommandError
from .remote import run_cmd

logger = logging.getLogger(__name__)


async def list_windows(connection, session):
    command = (
        "tmux list-w -t {} -F "
        "'#{{session_name}} #{{window_name}} #{{pane_pid}} "
        "#{{pane_dead}} #{{pane_dead_status}}'"
    ).format(shlex.quote(session))
    returncode, stdout, stderr = await run_cmd(
        connection, command, throw_on_failure=False
    )
    if returncode == 1:
        return {}
    if returncode != 0:
        raise CommandError(command, returncode, stderr)

    result = {}
    for line in stdout.splitlines():
        tokens = line.strip().split()
        if len(tokens) == 4:
            tokens.append("0")
        if len(tokens) != 5:
            logger.warning("ignoring unexpected tmux row: %r", line)
            continue
        session_name, window, pid, dead, dead_status = tokens
        if session_name != session:
            continue
        result[window] = {
            "pid": int(pid),
            "dead": dead == "1",
            "exitstatus": int(dead_status),
            "run_pending": (
                await run_cmd(
                    connection,
                    "test -f /tmp/{}.STARTING".format(window),
                    throw_on_failure=False,
                )
            )[0]
            == 0,
            "kill_pending": (
                await run_cmd(
                    connection,
                    "test -f /tmp/{}.KILLING".format(window),
                    throw_on_failure=False,
                )
            )[0]
            == 0,
        }
    return result


async def has_window(connection, session, window):
    target = "{}:{}".format(session, window)
    command = "tmux has-session -t {}".format(shlex.quote(target))
    returncode, _, stderr = await run_cmd(
        connection, command, throw_on_failure=False
    )
    if returncode == 0:
        return True
    if returncode == 1:
        return False
    if returncode == 127:
        raise CommandError(
            command,
            returncode,
            "tmux is not installed or is not available in PATH",
        )
    raise CommandError(command, returncode, stderr)


async def window_alive(connection, session, window):
    if not await has_window(connection, session, window):
        return False
    windows = await list_windows(connection, session)
    return window in windows and not windows[window]["dead"]


_spawn_lock_value = None
_spawn_lock_loop = None


def _spawn_lock():
    global _spawn_lock_value, _spawn_lock_loop
    loop = asyncio.get_event_loop()
    if _spawn_lock_value is None or _spawn_lock_loop is not loop:
        _spawn_lock_value = asyncio.Lock()
        _spawn_lock_loop = loop
    return _spawn_lock_value


async def spawn_window(connection, session, window, cmd):
    async with _spawn_lock():
        return await _spawn_window(connection, session, window, cmd)


async def _spawn_window(connection, session, window, cmd):
    windows = await list_windows(connection, session)
    quoted_cmd = shlex.quote(cmd)
    quoted_session = shlex.quote(session)
    quoted_window = shlex.quote(window)

    if not windows:
        commands = [
            (
                "tmux new-session -d -s {s} -n {w} "
                "/tmp/concert_launcher_wrapper.bash {w} {c}"
            ).format(s=quoted_session, w=quoted_window, c=quoted_cmd),
            "tmux set -t {} aggressive-resize on".format(quoted_session),
            "tmux set -t {} mouse on".format(quoted_session),
            "tmux set -t {} remain-on-exit on".format(quoted_session),
            "tmux set -t {} history-limit 10000".format(quoted_session),
        ]
        await run_cmd(connection, " && ".join(commands))
    elif window not in windows:
        commands = [
            (
                "tmux new-window -d -a -t {s} -n {w} "
                "/tmp/concert_launcher_wrapper.bash {w} {c}"
            ).format(s=quoted_session, w=quoted_window, c=quoted_cmd),
            "tmux set -t {s}:{w} aggressive-resize on".format(
                s=quoted_session, w=quoted_window
            ),
        ]
        await run_cmd(connection, " && ".join(commands))
    elif windows[window]["dead"]:
        await run_cmd(
            connection,
            (
                "tmux respawn-window -t {s}:{w} "
                "/tmp/concert_launcher_wrapper.bash {w} {c}"
            ).format(s=quoted_session, w=quoted_window, c=quoted_cmd),
        )
    else:
        raise CommandError(
            "tmux new-window",
            stderr="window {} exists and is not dead".format(window),
        )

    await run_cmd(
        connection,
        (
            "tmux set -t {s}:{w} remain-on-exit on && "
            "tmux set -t {s}:{w} history-limit 10000"
        ).format(s=quoted_session, w=quoted_window),
    )


# Historical names kept for downstream imports.
tmux_ls = list_windows
tmux_has_session = has_window
tmux_session_alive = window_alive
tmux_spawn_new_session = spawn_window
