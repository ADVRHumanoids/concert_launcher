"""Stop dependency graphs without touching foreign tmux windows.

Dependants stop before their dependencies, persistent processes receive
terminal-native signals through tmux, and connection failures invalidate the
shared SSH cache before propagating to callers.
"""

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
    """Stop one graph root, or every configured process when omitted."""
    registry = TaskRegistry()

    # Reverse graph traversal mirrors startup: cycles are explicit and shared
    # nodes are stopped once even when multiple dependants reach them.
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
            # Preserve configuration order for predictable top-level output;
            # TaskRegistry still deduplicates recursive dependant traversal.
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
    """Stop one node after all persistent dependants have stopped."""
    config = launcher.process(process, level=level, notify_event=notify_event)
    await config.connect()

    # Refuse a foreign same-name window before writing markers or signals.
    if config.persistent:
        windows = await tmux.list_windows(config.ssh, config.session)
        existing = windows.get(process)
        if existing is not None:
            tmux.require_managed_window(config.session, process, existing)

    marker_created = False
    try:
        # Status exposes STOPPING while this operation is in progress. Cleanup
        # is best-effort in ``finally`` so failures do not leave stale state.
        await remote.run_cmd(config.ssh, "touch /tmp/{}.KILLING".format(process))
        marker_created = True

        # A dependency cannot be stopped while a configured persistent
        # dependant still relies on it, so dependants are handled first.
        dependants = _dependants(launcher.cfg, process)
        if dependants:
            await config.print("stopping dependants: {}".format(", ".join(dependants)))
            await asyncio.gather(
                *[schedule(name, level + 1, stack) for name in dependants]
            )

        # One-shot nodes have no tmux process of their own. Their dependencies
        # still participate in graph-wide shutdown.
        if not config.persistent:
            if config.deps:
                await config.print("stopping dependencies")
                await asyncio.gather(
                    *[schedule(name, level + 1, stack) for name in config.deps]
                )
            return True

        # Re-read tmux after dependant shutdown because the target may have
        # changed state while recursive work was running.
        windows = await tmux.list_windows(config.ssh, config.session)
        info = windows.get(process)
        if info is None:
            await config.print("not running")
            return True
        tmux.require_managed_window(config.session, process, info)
        if info["dead"]:
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
    """Return persistent processes which directly depend on ``process``."""
    result = []
    for name, field in cfg.items():
        if name in ("context", process):
            continue
        field = field or {}
        if process in field.get("depends", []) and field.get("persistent", True):
            result.append(name)
    return result


async def _send_stop_signal(config, process, graceful):
    """Send SIGINT first, then escalate to SIGQUIT after five seconds."""
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

    Sending Ctrl-C or Ctrl-\\ through tmux lets the terminal driver target the
    actual foreground process group, including commands launched by a shell.
    """
    key = "C-c" if signal_name == "INT" else "C-\\"
    target = "{}:{}".format(config.session, process)
    command = "tmux send-keys -t {} {}".format(
        shlex.quote(target),
        shlex.quote(key),
    )
    await remote.run_cmd(config.ssh, command)
