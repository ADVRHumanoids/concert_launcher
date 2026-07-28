import asyncio
import unittest

from concert_launcher.errors import RemoteConnectionError
from concert_launcher.launcher import Launcher


class FakeManager:
    def __init__(self):
        self.invalidated = []

    async def invalidate(self, machine):
        self.invalidated.append(machine)

    async def get(self, machine):
        return "connection:{}".format(machine)

    async def close_all(self):
        return None


class LauncherRecoveryTests(unittest.TestCase):
    def run_async(self, coroutine):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coroutine)
        finally:
            loop.close()

    def test_execute_with_recovery_retries_typed_transport_error(self):
        manager = FakeManager()
        launcher = Launcher(
            {"context": {"session": "robot"}},
            connection_manager=manager,
        )
        attempts = []

        async def execute(*args, **kwargs):
            del args, kwargs
            attempts.append(1)
            if len(attempts) == 1:
                raise RemoteConnectionError(
                    "operator@robot-pc", "run command", OSError("offline")
                )
            return True

        launcher.execute_process = execute

        async def scenario():
            result = await launcher.execute_with_recovery(
                "controller", retries=1, retry_delay=0
            )
            self.assertTrue(result)
            self.assertEqual(len(attempts), 2)
            self.assertEqual(manager.invalidated, ["operator@robot-pc"])

        self.run_async(scenario())

    def test_recover_can_reconnect_immediately(self):
        manager = FakeManager()
        launcher = Launcher(
            {"context": {"session": "robot"}},
            connection_manager=manager,
        )

        async def scenario():
            error = RemoteConnectionError(
                "operator@robot-pc", "connect", OSError("offline")
            )
            connection = await launcher.recover(error)
            self.assertEqual(connection, "connection:operator@robot-pc")
            self.assertEqual(manager.invalidated, ["operator@robot-pc"])

        self.run_async(scenario())
