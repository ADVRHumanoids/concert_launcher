"""Stop process dependency graphs."""

import asyncio
import logging

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
    signal_name = "SIGINT" if use_graceful else "SIGQUIT"
    signal_key = "C-c" if use_graceful else "C-\\"
    await config.notify_state("Stopping")
    await config.print("stopping with {}".format(signal_name))
    await remote.run_cmd(
        config.ssh,
        "tmux send-keys -t {}:{} {} C-m Enter".format(
            config.session, process, signal_key
        ),
    )

    attempts = 0
    while await tmux.window_alive(config.ssh, config.session, process):
        await asyncio.sleep(1)
        attempts += 1
        if attempts > 5 and use_graceful:
            use_graceful = False
            await config.print("escalating to SIGQUIT")
            await remote.run_cmd(
                config.ssh,
                "tmux send-keys -t {}:{} C-\\ C-m Enter".format(
                    config.session, process
                ),
            )
