import os

import pytest

from .helpers import machine, unique_name


pytestmark = [pytest.mark.docker, pytest.mark.asyncio]


async def test_one_shot_command_executes_on_remote_host(
    launcher_factory,
    remote_a,
):
    session = unique_name("oneshot_session")
    process = unique_name("oneshot")
    marker = f"/tmp/{process}.remote-marker"
    messages = []

    async def notify(name, message):
        messages.append((name, message))

    config = {
        "context": {"session": session},
        process: {
            "machine": machine("A"),
            "persistent": False,
            "cmd": f"printf 'hello-over-ssh\\n'; printf remote > {marker}",
        },
    }
    launcher = launcher_factory(config)

    try:
        assert await launcher.execute_process(process, notify_event=notify) is True
        assert await remote_a.run(f"cat {marker}") == "remote"
        assert (
            await remote_a.run(
                "test -x /tmp/concert_launcher_wrapper.bash && "
                "test -r /tmp/concert_launcher_print_ps_tree.py && echo installed"
            )
            == "installed"
        )
        assert not os.path.exists(marker)
        assert any("hello-over-ssh" in message for _, message in messages)
    finally:
        await remote_a.run(f"rm -f {marker}", check=False)
        await remote_a.cleanup(session, [process])
