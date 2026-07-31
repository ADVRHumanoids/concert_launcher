"""Stop process dependency graphs."""

import asyncio
import logging
import shlex

from . import remote, tmux
from .errors import ConfigurationError, RemoteConnectionError
from .operations import TaskRegistry

logger = logging.getLogger(__name__)


async def kill(
    launcher,
    process=None,
    graceful=True,
    notify_event=None,
):
    registry = TaskRegistry()

    async def schedule(name, level, stack):
        if name in stack:
            cycle = " -> ".join(stack + (name,))
            raise ConfigurationError("kill dependency cycle detected: {}".format(cycle))
        return await registry.run_once(
            name,
            lambda: _kill_one(
                launcher,
                name,
                graceful,
                notify_event,
                level,
                stack + (name,),
                schedule,
            ),
        )

    try:
        if process is None:
            names = [name for name in launcher.cfg if name != "context"]
            results = []
            for name in names:
                results.append(await schedule(name, 1, tuple()))
            return all(results)
        return await schedule(process, 0, tuple())
    except RemoteConnectionError as exc:
        await launcher.connection_manager.invalidate(exc.machine)
        raise


async def _kill_one(
    launcher,
    process,
    graceful,
    notify_event,
    level,
    stack,
    schedule,
):
    config = launcher.process(process, level=level, notify_event=notify_event)
    await config.connect()
    marker_created = False
    try:
        await remote.run_cmd(config.ssh, "touch /tmp/{}.KILLING".format(process))
        marker_created = True

        dependants = _dependants(launcher.cfg, process)
        if dependants:
            await config.print("stopping dependants: {}".format(", ".join(dependants)))
            await asyncio.gather(
                *[schedule(name, level + 1, stack) for name in dependants]
            )

        if not config.persistent:
            if config.deps:
                await config.print("stopping dependencies")
                await asyncio.gather(
                    *[schedule(name, level + 1, stack) for name in config.deps]
                )
            return True

        windows = await tmux.list_windows(config.ssh, config.session)
        if process not in windows:
            await config.print("not running")
            return True
        if windows[process]["dead"]:
            await config.print("already stopped")
            return True

        await _send_stop_signal(config, process, graceful)
        await config.print("killed")
        return True
    finally:
        if marker_created:
            try:
                await remote.run_cmd(
                    config.ssh,
                    "rm -f /tmp/{}.KILLING".format(process),
                    throw_on_failure=False,
                )
            except Exception:
                logger.debug("could not remove kill marker", exc_info=True)


def _dependants(cfg, process):
    result = []
    for name, field in cfg.items():
        if name in ("context", process):
            continue
        field = field or {}
        if process in field.get("depends", []) and field.get("persistent", True):
            result.append(name)
    return result


async def _send_stop_signal(config, process, graceful):
    use_graceful = graceful and not config.force_sigquit
    signal_name = "INT" if use_graceful else "QUIT"
    await config.notify_state("Stopping")
    await config.print("stopping with SIG{}".format(signal_name))
    await _send_tmux_signal_key(config, process, signal_name)

    attempts = 0
    while await tmux.window_alive(config.ssh, config.session, process):
        await asyncio.sleep(1)
        attempts += 1
        if attempts > 5 and use_graceful:
            use_graceful = False
            await config.print("escalating to SIGQUIT")
            await _send_tmux_signal_key(config, process, "QUIT")


async def _send_tmux_signal_key(config, process, signal_name):
    """Deliver a terminal signal to the current tmux foreground process.

    Looking up a process group from the pane PID is racy: interactive shells
    move each foreground child into its own group. Sending the corresponding
    control key through tmux lets the terminal driver target the actual
    foreground process group, matching an operator pressing Ctrl-C or Ctrl-\\.
    """
    key = "C-c" if signal_name == "INT" else "C-\\"
    target = "{}:{}".format(config.session, process)
    command = "tmux send-keys -t {} {}".format(
        shlex.quote(target),
        shlex.quote(key),
    )
    await remote.run_cmd(config.ssh, command)
