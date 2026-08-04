import asyncio

import pytest

from .helpers import cancel_task, machine, unique_name, wait_for_queue


pytestmark = [pytest.mark.docker, pytest.mark.asyncio]


async def test_stream_output_and_return_remote_exit_status(
    launcher_factory,
    remote_a,
):
    session = unique_name("wait_session")
    process = unique_name("finite")
    config = {
        "context": {"session": session},
        process: {
            "machine": machine("A"),
            "cmd": "echo READY; sleep 2; echo DONE; exit 17",
        },
    }
    launcher = launcher_factory(config)
    lines = asyncio.Queue()

    def printer_factory(name):
        async def collect(line):
            await lines.put((name, line))
        return collect

    watch_task = None
    try:
        assert await launcher.execute_process(process) is True

        status = await launcher.status(process)
        assert status[session][process]["state"] == "RUNNING"

        watch_task = asyncio.create_task(
            launcher.watch(
                process,
                printer_coro_factory=printer_factory,
                num_lines="+1",
            )
        )
        name, line = await wait_for_queue(
            lines,
            lambda item: "READY" in item[1],
        )
        assert name == process
        assert "READY" in line

        assert await launcher.wait_process(
            process,
            timeout=10,
            watch_output=False,
        ) == 17

        status = await launcher.status(process)
        entry = status[session][process]
        assert entry["state"] == "DEAD"
        assert entry["exitstatus"] == 17
        assert "DONE" in await remote_a.run(f"cat /tmp/{process}.stdout")
    finally:
        if watch_task is not None:
            await cancel_task(watch_task)
        await remote_a.cleanup(session, [process])


async def test_graceful_kill_delivers_sigint_to_remote_process(
    launcher_factory,
    remote_a,
):
    session = unique_name("kill_session")
    process = unique_name("signal_receiver")
    signal_file = f"/tmp/{process}.signal"
    ready_file = f"/tmp/{process}.ready"
    config = {
        "context": {"session": session},
        process: {
            "machine": machine("A"),
            "cmd": (
                f"python3 /usr/local/bin/concert-signal-receiver "
                f"{signal_file} {ready_file}"
            ),
            "ready_check": f"test -f {ready_file}",
        },
    }
    launcher = launcher_factory(config)

    try:
        assert await launcher.execute_process(process) is True
        assert await launcher.kill(process, graceful=True) is True

        status = await launcher.status(process)
        entry = status[session][process]
        assert entry["state"] == "STOPPED"
        assert await remote_a.run(f"cat {signal_file}") == "SIGINT"
        assert "process exited with code 0" in await remote_a.run(
            f"cat /tmp/{process}.stdout"
        )
    finally:
        await remote_a.run(
            f"rm -f {signal_file} {ready_file}",
            check=False,
        )
        await remote_a.cleanup(session, [process])
