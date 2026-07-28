import asyncio
import unittest

from concert_launcher.connections import ConnectionManager
from concert_launcher.errors import RemoteConnectionError


class FakeConnection:
    def __init__(self, closed=False):
        self.closed = closed
        self.close_calls = 0
        self.wait_calls = 0

    def is_closed(self):
        return self.closed

    def close(self):
        self.close_calls += 1
        self.closed = True

    async def wait_closed(self):
        self.wait_calls += 1


class ConnectionManagerTests(unittest.TestCase):
    def run_async(self, coroutine):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coroutine)
        finally:
            loop.close()

    def test_failed_connection_is_not_cached_and_next_attempt_can_recover(self):
        attempts = []
        connection = FakeConnection()

        async def connect(**kwargs):
            attempts.append(kwargs)
            if len(attempts) == 1:
                raise OSError("host unreachable")
            return connection

        manager = ConnectionManager(connect=connect)

        async def scenario():
            with self.assertRaises(RemoteConnectionError) as raised:
                await manager.get("robot@10.0.0.2")
            self.assertEqual(raised.exception.machine, "robot@10.0.0.2")
            self.assertTrue(raised.exception.retryable)
            recovered = await manager.get("robot@10.0.0.2")
            self.assertIs(recovered, connection)
            self.assertEqual(len(attempts), 2)

        self.run_async(scenario())

    def test_closed_cached_connection_is_replaced(self):
        first = FakeConnection()
        second = FakeConnection()
        connections = [first, second]

        async def connect(**kwargs):
            del kwargs
            return connections.pop(0)

        manager = ConnectionManager(connect=connect)

        async def scenario():
            self.assertIs(await manager.get("robot@host"), first)
            first.closed = True
            self.assertIs(await manager.get("robot@host"), second)
            self.assertEqual(first.close_calls, 1)
            self.assertEqual(first.wait_calls, 1)

        self.run_async(scenario())

    def test_invalidate_closes_cached_connection(self):
        connection = FakeConnection()

        async def connect(**kwargs):
            del kwargs
            return connection

        manager = ConnectionManager(connect=connect)

        async def scenario():
            await manager.get("robot@host")
            await manager.invalidate("robot@host")
            self.assertEqual(connection.close_calls, 1)
            self.assertEqual(connection.wait_calls, 1)

        self.run_async(scenario())


class RemoteOperationTests(unittest.TestCase):
    def run_async(self, coroutine):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coroutine)
        finally:
            loop.close()

    def test_remote_command_failure_is_normalized(self):
        from concert_launcher import remote

        class BrokenConnection:
            _username = "operator"
            _host = "robot-pc"

            async def run(self, *args, **kwargs):
                del args, kwargs
                raise OSError("connection reset")

        async def scenario():
            with self.assertRaises(RemoteConnectionError) as raised:
                await remote.run_cmd(BrokenConnection(), "true")
            self.assertEqual(raised.exception.machine, "operator@robot-pc")
            self.assertIn("connection reset", str(raised.exception))

        self.run_async(scenario())
