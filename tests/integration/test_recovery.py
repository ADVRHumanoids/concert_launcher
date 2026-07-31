import asyncio
import re

import pytest

from concert_launcher.errors import RemoteConnectionError

from .helpers import (
    cancel_task,
    machine,
    unique_name,
    wait_for_queue,
    wait_until,
)


pytestmark = [pytest.mark.docker, pytest.mark.chaos, pytest.mark.asyncio]


async def _tick_count(remote, process):
    output = await remote.run(
        f"grep -c 'tick-' /tmp/{process}.stdout || true",
        check=False,
    )
    return int(output or "0")


async def test_tmux_process_survives_ssh_outage_and_manual_recovery(
    launcher_factory,
    remote_a,
    proxy_a,
):
    session = unique_name("survival_session")
    process = unique_name("heartbeat")
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
        before = await _tick_count(remote_a, process)

        await proxy_a.disable()
        with pytest.raises(RemoteConnectionError):
            await launcher.status(process)

        await wait_until(
            lambda: _tick_count(remote_a, process),
            timeout=5,
        )
        await asyncio.sleep(0.8)
        after = await _tick_count(remote_a, process)
        assert after > before
        assert await remote_a.run(
            f"tmux has-session -t {session}:{process}; echo $?",
            check=False,
        ) == "0"

        await proxy_a.enable()
        await launcher.recover(machine("A"))
        status = await launcher.status(process)
        assert status[session][process]["state"] == "RUNNING"
    finally:
        await proxy_a.enable()
        try:
            await launcher.recover(machine("A"))
            await launcher.kill(process, graceful=True)
        except Exception:
            pass
        await remote_a.cleanup(session, [process])


async def test_output_watch_resumes_without_duplicate_ticks_after_outage(
    launcher_factory,
    remote_a,
    proxy_a,
):
    session = unique_name("watch_recovery_session")
    process = unique_name("watch_heartbeat")
    config = {
        "context": {"session": session},
        process: {
            "machine": machine("A"),
            "cmd": "python3 /usr/local/bin/concert-heartbeat",
            "ready_check": f"grep -q 'tick-2' /tmp/{process}.stdout",
        },
    }
    launcher = launcher_factory(config)
    lines = asyncio.Queue()
    seen_ticks = []

    def printer_factory(name):
        assert name == process

        async def collect(line):
            match = re.search(r"tick-(\d+)", line)
            if match:
                tick = int(match.group(1))
                seen_ticks.append(tick)
                await lines.put(tick)

        return collect

    watch_task = None
    try:
        assert await launcher.execute_process(process) is True
        watch_task = asyncio.create_task(
            launcher.watch_with_recovery(
                process,
                printer_coro_factory=printer_factory,
                num_lines="+1",
                retries=40,
                retry_delay=0.1,
            )
        )
        first_tick = await wait_for_queue(lines, lambda tick: tick >= 2)

        await proxy_a.disable()
        await wait_until(
            lambda: _tick_count(remote_a, process),
            timeout=5,
        )
        await asyncio.sleep(1.0)
        outage_tick = await _tick_count(remote_a, process)
        assert outage_tick > first_tick

        await proxy_a.enable()
        resumed_tick = await wait_for_queue(
            lines,
            lambda tick: tick >= outage_tick,
            timeout=10,
        )
        assert resumed_tick >= outage_tick
        assert watch_task.done() is False

        unique_ticks = sorted(set(seen_ticks))
        assert len(unique_ticks) == len(seen_ticks)
        assert unique_ticks == list(range(unique_ticks[0], unique_ticks[-1] + 1))
    finally:
        await proxy_a.enable()
        if watch_task is not None:
            await cancel_task(watch_task)
        try:
            await launcher.recover(machine("A"))
            await launcher.kill(process, graceful=True)
        except Exception:
            pass
        await remote_a.cleanup(session, [process])
