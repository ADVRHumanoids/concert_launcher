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

    def test_watch_with_recovery_resumes_after_delivered_lines(self):
        manager = FakeManager()
        launcher = Launcher(
            {"context": {"session": "robot"}},
            connection_manager=manager,
        )
        attempts = []
        output = []

        def printer_factory(name):
            self.assertEqual(name, "controller")

            async def collect(line):
                output.append(line)

            return collect

        async def watch(process, printer_coro_factory=None, num_lines="+1"):
            attempts.append(num_lines)
            printer = printer_coro_factory(process)
            if len(attempts) == 1:
                await printer("first\n")
                await printer("second\n")
                raise RemoteConnectionError(
                    "operator@robot-pc", "watch process output", OSError("offline")
                )
            await printer("third\n")
            return True

        launcher.watch = watch

        async def scenario():
            result = await launcher.watch_with_recovery(
                "controller",
                printer_coro_factory=printer_factory,
                retries=1,
                retry_delay=0,
            )
            self.assertTrue(result)
            self.assertEqual(attempts, ["+1", "+3"])
            self.assertEqual(output, ["first\n", "second\n", "third\n"])
            self.assertEqual(manager.invalidated, ["operator@robot-pc"])

        self.run_async(scenario())

    def test_watch_with_recovery_retries_unexpected_remote_eof(self):
        manager = FakeManager()
        launcher = Launcher(
            {
                "context": {"session": "robot"},
                "controller": {
                    "machine": "operator@robot-pc",
                    "cmd": "run-controller",
                },
            },
            connection_manager=manager,
        )
        attempts = []

        async def watch(process, printer_coro_factory=None, num_lines="+1"):
            del process, printer_coro_factory
            attempts.append(num_lines)
            return None if len(attempts) == 1 else True

        launcher.watch = watch

        async def scenario():
            result = await launcher.watch_with_recovery(
                "controller", retries=1, retry_delay=0
            )
            self.assertTrue(result)
            self.assertEqual(attempts, ["+1", "+1"])
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
