import pytest

from .helpers import machine, unique_name, unique_port


pytestmark = [pytest.mark.docker, pytest.mark.asyncio]


async def test_dependency_becomes_ready_on_host_a_before_consumer_runs_on_host_b(
    launcher_factory,
    remote_a,
    remote_b,
):
    session = unique_name("cross_host_session")
    dependency = unique_name("service")
    consumer = unique_name("consumer")
    marker = f"/tmp/{consumer}.dependency-seen"
    port = unique_port()
    events = []

    async def notify(name, message):
        events.append((name, message))

    config = {
        "context": {"session": session},
        dependency: {
            "machine": machine("A"),
            "cmd": f"python3 -m http.server {port} --bind 0.0.0.0",
            "ready_check": f"nc -z -w 1 127.0.0.1 {port}",
        },
        consumer: {
            "machine": machine("B"),
            "persistent": False,
            "depends": [dependency],
            "cmd": (
                f"nc -z -w 2 ssh-a {port} && "
                f"printf dependency-seen > {marker}"
            ),
        },
    }
    launcher = launcher_factory(config)

    try:
        assert await launcher.execute_process(consumer, notify_event=notify) is True
        assert await remote_b.run(f"cat {marker}") == "dependency-seen"

        dependency_ready = events.index((dependency, "state is Ready"))
        consumer_started = next(
            index
            for index, event in enumerate(events)
            if event == (consumer, "running one-shot command")
        )
        assert dependency_ready < consumer_started
        assert "1" == await remote_a.run(
            f"tmux list-w -t {session} -F '#{{pane_dead}}'"
            f" | grep -c '^0$'"
        )
    finally:
        await remote_b.run(f"rm -f {marker}", check=False)
        await remote_a.cleanup(session, [dependency, consumer])
        await remote_b.cleanup(session, [dependency, consumer])
