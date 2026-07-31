import asyncio

import pytest

from concert_launcher.errors import ProcessError

from .helpers import machine, unique_name, wait_until


pytestmark = [pytest.mark.docker, pytest.mark.asyncio]


async def _pane_pid(remote, target):
    return await remote.run(
        f"tmux display-message -p -t {target} '#{{pane_pid}}'"
    )


async def _pane_alive(remote, target):
    return (
        await remote.run(
            f"tmux display-message -p -t {target} '#{{pane_dead}}'",
            check=False,
        )
        == "0"
    )


async def test_foreign_sessions_and_windows_are_left_untouched(
    launcher_factory,
    remote_a,
):
    session = unique_name("shared_session")
    foreign_session = unique_name("foreign_session")
    foreign_window = unique_name("sidecar")
    standalone_window = unique_name("standalone")
    process = unique_name("managed")
    shared_target = f"{session}:{foreign_window}"
    standalone_target = f"{foreign_session}:{standalone_window}"

    await remote_a.run(
        f"tmux new-session -d -s {foreign_session} -n {standalone_window} "
        "'python3 /usr/local/bin/concert-heartbeat'"
    )
    await remote_a.run(
        f"tmux new-session -d -s {session} -n {foreign_window} "
        "'python3 /usr/local/bin/concert-heartbeat'"
    )
    await wait_until(lambda: _pane_alive(remote_a, shared_target))
    await wait_until(lambda: _pane_alive(remote_a, standalone_target))
    shared_pid = await _pane_pid(remote_a, shared_target)
    standalone_pid = await _pane_pid(remote_a, standalone_target)

    config = {
        "context": {"session": session},
        process: {
            "machine": machine("A"),
            "cmd": "python3 /usr/local/bin/concert-heartbeat",
            "ready_check": f"grep -q 'tick-2' /tmp/{process}.stdout",
        },
    }
    launcher = launcher_factory(config)

    try:
        assert await launcher.execute_process(process) is True
        assert await remote_a.run(
            f"tmux show-options -w -v -t {session}:{process} "
            "@concert_launcher_managed"
        ) == "1"

        status = await launcher.status()
        assert status[session][process]["state"] == "RUNNING"
        assert foreign_window not in status[session]

        assert await launcher.kill() is True
        assert await _pane_alive(remote_a, shared_target)
        assert await _pane_alive(remote_a, standalone_target)
        assert await _pane_pid(remote_a, shared_target) == shared_pid
        assert await _pane_pid(remote_a, standalone_target) == standalone_pid
        assert await remote_a.run(
            f"tmux show-options -w -v -t {shared_target} "
            "@concert_launcher_managed 2>/dev/null || true"
        ) == ""
    finally:
        await remote_a.run(
            f"tmux kill-session -t {session} >/dev/null 2>&1 || true; "
            f"tmux kill-session -t {foreign_session} >/dev/null 2>&1 || true",
            check=False,
        )


async def test_same_name_foreign_window_is_reported_and_never_controlled(
    launcher_factory,
    remote_a,
):
    session = unique_name("collision_session")
    process = unique_name("collision")
    target = f"{session}:{process}"
    await remote_a.run(
        f"tmux new-session -d -s {session} -n {process} "
        "'python3 /usr/local/bin/concert-heartbeat'"
    )
    await wait_until(lambda: _pane_alive(remote_a, target))
    original_pid = await _pane_pid(remote_a, target)

    config = {
        "context": {"session": session},
        process: {
            "machine": machine("A"),
            "cmd": "python3 /usr/local/bin/concert-heartbeat",
        },
    }
    launcher = launcher_factory(config)

    try:
        status = await launcher.status(process)
        entry = status[session][process]
        assert entry["state"] == "CONFLICT"
        assert entry["managed"] is False
        assert "unmanaged tmux window" in entry["error"]

        with pytest.raises(ProcessError, match="unmanaged tmux window"):
            await launcher.execute_process(process)
        with pytest.raises(ProcessError, match="unmanaged tmux window"):
            await launcher.kill(process)
        with pytest.raises(ProcessError, match="unmanaged tmux window"):
            await launcher.pstree(process)
        with pytest.raises(ProcessError, match="unmanaged tmux window"):
            await launcher.wait_process(process, watch_output=False)
        with pytest.raises(ProcessError, match="unmanaged tmux window"):
            await asyncio.wait_for(launcher.watch(process), timeout=3)

        assert await remote_a.run(
            f"test ! -e /tmp/{process}.STARTING && "
            f"test ! -e /tmp/{process}.KILLING; echo $?",
            check=False,
        ) == "0"
        assert await _pane_alive(remote_a, target)
        assert await _pane_pid(remote_a, target) == original_pid
    finally:
        await remote_a.run(
            f"tmux kill-session -t {session} >/dev/null 2>&1 || true",
            check=False,
        )


async def test_legacy_launcher_window_without_tag_remains_manageable(
    launcher_factory,
    remote_a,
):
    session = unique_name("legacy_session")
    process = unique_name("legacy")
    target = f"{session}:{process}"
    config = {
        "context": {"session": session},
        process: {
            "machine": machine("A"),
            "cmd": "python3 /usr/local/bin/concert-heartbeat",
            "ready_check": f"grep -q 'tick-2' /tmp/{process}.stdout",
        },
    }
    launcher = launcher_factory(config)

    try:
        assert await launcher.execute_process(process) is True
        await remote_a.run(
            f"tmux set-option -w -u -t {target} @concert_launcher_managed"
        )

        status = await launcher.status(process)
        entry = status[session][process]
        assert entry["state"] == "RUNNING"
        assert entry["managed"] is True
        assert entry["legacy_managed"] is True

        assert await launcher.kill(process, graceful=True) is True
        status = await launcher.status(process)
        assert status[session][process]["state"] == "DEAD"
    finally:
        await remote_a.cleanup(session, [process])
