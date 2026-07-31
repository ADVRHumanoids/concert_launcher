"""Start one process and its dependency graph in dependency-first order.

Persistent processes are supervised by tmux; one-shot processes run directly.
Every remote transport error invalidates the cached connection before it is
re-raised to the library caller.
"""

import asyncio
import logging
import time

from . import remote, tmux
from .errors import ConfigurationError, ProcessError, RemoteConnectionError
from .operations import TaskRegistry

logger = logging.getLogger(__name__)


async def execute_process(
    launcher,
    process,
    params=None,
    variants=None,
    notify_event=None,
):
    """Execute the requested graph root exactly once per dependency node."""
    registry = TaskRegistry()
    params = params or {}
    variants = variants or []

    # Recursive scheduling builds the dependency graph lazily. ``stack`` finds
    # cycles, while TaskRegistry merges paths which reach the same dependency.
    async def schedule(name, level, stack):
        if name in stack:
            cycle = " -> ".join(stack + (name,))
            raise ConfigurationError("dependency cycle detected: {}".format(cycle))
        return await registry.run_once(
            name,
            lambda: _execute_one(
                launcher,
                name,
                params,
                variants,
                notify_event,
                level,
                stack + (name,),
                schedule,
            ),
        )

    try:
        return await schedule(process, 0, tuple())
    except RemoteConnectionError as exc:
        # Never leave a failed transport available for the next API call.
        await launcher.connection_manager.invalidate(exc.machine)
        raise


async def _execute_one(
    launcher,
    process,
    params,
    variants,
    notify_event,
    level,
    stack,
    schedule,
):
    """Start one graph node after its dependencies are ready."""
    config = launcher.process(process, level=level, notify_event=notify_event)
    await config.notify_state("Connecting")
    await config.connect()

    # Ownership is checked before creating marker files or altering tmux. A
    # same-name foreign window must fail safely without any launcher side effect.
    if config.persistent:
        windows = await tmux.list_windows(config.ssh, config.session)
        existing = windows.get(process)
        if existing is not None:
            tmux.require_managed_window(config.session, process, existing)

    marker_created = False
    try:
        # Status uses this marker to distinguish STARTING from a normal running
        # pane. It is removed in ``finally`` even if dependency startup fails.
        await remote.run_cmd(config.ssh, "touch /tmp/{}.STARTING".format(process))
        marker_created = True

        # Dependencies are scheduled concurrently, but this node does not start
        # until every dependency task has completed its readiness phase.
        if config.deps:
            await config.notify_state("WaitingDependencies")
            for dependency in config.deps:
                await config.print("depends on {}".format(dependency))
            await asyncio.gather(
                *[
                    schedule(dependency, level + 1, stack)
                    for dependency in config.deps
                ]
            )

        command = config.parse_cmd(params, variants)
        if not config.persistent:
            return await _run_one_shot(config, command)

        # Existing live managed windows make start idempotent. Dead managed
        # windows are respawned by the tmux layer with ownership preserved.
        if await tmux.window_alive(config.ssh, config.session, process):
            await config.print("already running")
        else:
            await config.notify_state("Starting")
            await config.print("starting")
            await tmux.spawn_window(config.ssh, config.session, process, command)

        # Readiness is part of successful startup, not a separate background
        # activity: callers return only after the configured check succeeds.
        await _wait_until_ready(config, process)
        await config.notify_state("Ready")
        await config.print("ready")
        return True
    finally:
        if marker_created:
            try:
                await remote.run_cmd(
                    config.ssh,
                    "rm -f /tmp/{}.STARTING".format(process),
                    throw_on_failure=False,
                )
            except Exception:
                logger.debug("could not remove start marker", exc_info=True)


async def _run_one_shot(config, command):
    """Run a finite command and report its captured output."""
    await config.print("running one-shot command")
    returncode, stdout, stderr = await remote.run_cmd(
        config.ssh,
        command,
        interactive=True,
        throw_on_failure=False,
    )
    for line in stdout.splitlines():
        await config.print("stdout | {}".format(line))
    for line in stderr.splitlines():
        await config.print("stderr | {}".format(line))
    if returncode != 0:
        await config.print("failed with exit code {}".format(returncode))
        return False
    await config.print("success")
    return True


async def _wait_until_ready(config, process):
    """Poll readiness while proving the managed tmux process stays alive."""
    if config.ready_check is None:
        return

    await config.notify_state("WaitingReady")
    while True:
        started = time.monotonic()
        await config.print("checking readiness")
        returncode, _, _ = await remote.run_cmd(
            config.ssh,
            config.ready_check,
            interactive=False,
            throw_on_failure=False,
        )
        if not await tmux.window_alive(config.ssh, config.session, process):
            raise ProcessError(
                "process {}:{} exited before becoming ready".format(
                    config.session, process
                )
            )
        if returncode == 0:
            return
        # Keep checks responsive without spinning when a fast command fails.
        await asyncio.sleep(max(0.0, 0.666 - (time.monotonic() - started)))
