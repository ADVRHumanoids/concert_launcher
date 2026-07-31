"""Tmux process-management primitives."""

import asyncio
import logging
import shlex

from .errors import CommandError, ProcessError
from .remote import run_cmd

logger = logging.getLogger(__name__)

MANAGED_OPTION = "@concert_launcher_managed"
WRAPPER_PATH = "/tmp/concert_launcher_wrapper.bash"


async def list_windows(connection, session):
    command = (
        "tmux list-w -t {} -F "
        "'#{{session_name}}\t#{{window_name}}\t#{{window_id}}\t"
        "#{{pane_pid}}\t#{{pane_dead}}\texit=#{{pane_dead_status}}\t"
        "managed=#{{{}}}\t#{{pane_start_command}}'"
    ).format(shlex.quote(session), MANAGED_OPTION)
    returncode, stdout, stderr = await run_cmd(
        connection, command, throw_on_failure=False
    )
    if returncode == 1:
        return {}
    if returncode != 0:
        raise CommandError(command, returncode, stderr)

    result = {}
    for line in stdout.splitlines():
        tokens = [token.strip() for token in line.split("\t", 7)]
        if (
            len(tokens) != 8
            or not tokens[5].startswith("exit=")
            or not tokens[6].startswith("managed=")
        ):
            logger.warning("ignoring unexpected tmux row: %r", line)
            continue

        (
            session_name,
            window,
            window_id,
            pid,
            dead,
            exit_field,
            managed_field,
            start_command,
        ) = tokens
        if session_name != session:
            continue

        is_dead = dead == "1"
        dead_status = exit_field[len("exit="):]
        exitstatus = int(dead_status) if dead_status else (None if is_dead else 0)
        tagged = managed_field[len("managed="):] == "1"
        legacy_managed = start_command.startswith(WRAPPER_PATH + " ")
        managed = tagged or legacy_managed
        run_pending = False
        kill_pending = False
        if managed:
            run_pending = await _marker_exists(connection, window, ".STARTING")
            kill_pending = await _marker_exists(connection, window, ".KILLING")

        entry = {
            "id": window_id,
            "window_ids": [window_id],
            "pid": int(pid),
            "dead": is_dead,
            "exitstatus": exitstatus,
            "managed": managed,
            "legacy_managed": legacy_managed and not tagged,
            "ambiguous": False,
            "run_pending": run_pending,
            "kill_pending": kill_pending,
        }

        if window in result:
            previous = result[window]
            ids = list(previous.get("window_ids", [])) + [window_id]
            result[window] = {
                "id": None,
                "window_ids": ids,
                "pid": "-",
                "dead": False,
                "exitstatus": None,
                "managed": False,
                "legacy_managed": False,
                "ambiguous": True,
                "run_pending": False,
                "kill_pending": False,
            }
        else:
            result[window] = entry
    return result


async def _marker_exists(connection, window, suffix):
    path = shlex.quote("/tmp/{}{}".format(window, suffix))
    return (
        await run_cmd(
            connection,
            "test -f {}".format(path),
            throw_on_failure=False,
        )
    )[0] == 0


def window_conflict_message(session, window, info):
    if info is None:
        return None
    target = "{}:{}".format(session, window)
    if info.get("ambiguous"):
        return (
            "ambiguous tmux target {!r}: multiple windows have that name"
        ).format(target)
    if not info.get("managed"):
        return "unmanaged tmux window {!r}".format(target)
    return None


def require_managed_window(session, window, info):
    """Return a managed window or refuse to control a foreign collision."""
    message = window_conflict_message(session, window, info)
    if message is not None:
        raise ProcessError("refusing to control {}".format(message))
    return info


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
    windows = await list_windows(connection, session)
    info = windows.get(window)
    if info is None or info.get("ambiguous") or not info.get("managed"):
        return False
    return not info["dead"]


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
    target = "{}:{}".format(session, window)
    quoted_target = shlex.quote(target)
    tag_command = "tmux set-option -w -t {} {} 1".format(
        quoted_target,
        MANAGED_OPTION,
    )

    if not windows:
        commands = [
            (
                "tmux new-session -d -s {s} -n {w} "
                "/tmp/concert_launcher_wrapper.bash {w} {c}"
            ).format(s=quoted_session, w=quoted_window, c=quoted_cmd),
            tag_command,
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
            tag_command,
            "tmux set -t {target} aggressive-resize on".format(
                target=quoted_target
            ),
        ]
        await run_cmd(connection, " && ".join(commands))
    else:
        info = require_managed_window(session, window, windows[window])
        if info["dead"]:
            await run_cmd(
                connection,
                (
                    "tmux respawn-window -t {target} "
                    "/tmp/concert_launcher_wrapper.bash {w} {c} && {tag}"
                ).format(
                    target=quoted_target,
                    w=quoted_window,
                    c=quoted_cmd,
                    tag=tag_command,
                ),
            )
        else:
            raise CommandError(
                "tmux new-window",
                stderr="window {} exists and is not dead".format(window),
            )

    await run_cmd(
        connection,
        (
            "tmux set -t {target} remain-on-exit on && "
            "tmux set -t {target} history-limit 10000"
        ).format(target=quoted_target),
    )


# Historical names kept for downstream imports.
tmux_ls = list_windows
tmux_has_session = has_window
tmux_session_alive = window_alive
tmux_spawn_new_session = spawn_window
