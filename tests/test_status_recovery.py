import asyncio
import io
import unittest

from concert_launcher.errors import RemoteConnectionError
from concert_launcher.launcher import Launcher
from concert_launcher.output import ConsoleReporter


class OfflineManager:
    def __init__(self):
        self.invalidated = []

    async def get(self, machine):
        raise RemoteConnectionError(machine, "connect", OSError("offline"))

    async def invalidate(self, machine):
        self.invalidated.append(machine)

    async def close_all(self):
        return None


class StatusRecoveryTests(unittest.TestCase):
    def run_async(self, coroutine):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coroutine)
        finally:
            loop.close()

    def setUp(self):
        self.config = {
            "context": {"session": "robot"},
            "controller": {
                "cmd": "controller",
                "machine": "operator@robot-pc",
            },
        }

    def test_default_status_raises_typed_error(self):
        manager = OfflineManager()
        launcher = Launcher(self.config, connection_manager=manager)

        async def scenario():
            with self.assertRaises(RemoteConnectionError):
                await launcher.status()
            self.assertEqual(manager.invalidated, ["operator@robot-pc"])

        self.run_async(scenario())

    def test_dashboard_status_marks_host_unavailable(self):
        manager = OfflineManager()
        stream = io.StringIO()
        launcher = Launcher(
            self.config,
            connection_manager=manager,
            reporter=ConsoleReporter(stream=stream, color=False),
        )

        async def scenario():
            result = await launcher.status(
                print_to_stdout=True,
                raise_on_unavailable=False,
            )
            entry = result["robot"]["controller"]
            self.assertEqual(entry["state"], "UNAVAILABLE")
            self.assertIn("offline", entry["error"])
            self.assertIn("UNAVAILABLE", stream.getvalue())

        self.run_async(scenario())
