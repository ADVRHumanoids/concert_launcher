import asyncio
import unittest
from unittest import mock

from concert_launcher.launcher import Launcher


class LocalManager:
    async def get(self, machine):
        del machine
        return None

    async def invalidate(self, machine):
        del machine

    async def close_all(self):
        return None


class StatusStateTests(unittest.TestCase):
    def run_async(self, coroutine):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coroutine)
        finally:
            loop.close()

    def test_dead_pane_with_zero_exit_is_stopped(self):
        config = {
            "context": {"session": "robot"},
            "controller": {"cmd": "controller"},
        }
        launcher = Launcher(config, connection_manager=LocalManager())

        async def list_windows(_connection, _session):
            return {
                "controller": {
                    "dead": True,
                    "exitstatus": 0,
                    "managed": True,
                    "legacy_managed": False,
                    "ambiguous": False,
                    "run_pending": False,
                    "kill_pending": False,
                    "pid": 123,
                }
            }

        with mock.patch("concert_launcher.inspection.tmux.list_windows", list_windows):
            result = self.run_async(launcher.status("controller"))

        self.assertEqual(result["robot"]["controller"]["state"], "STOPPED")

    def test_dead_pane_with_nonzero_exit_is_dead(self):
        config = {
            "context": {"session": "robot"},
            "controller": {"cmd": "controller"},
        }
        launcher = Launcher(config, connection_manager=LocalManager())

        async def list_windows(_connection, _session):
            return {
                "controller": {
                    "dead": True,
                    "exitstatus": 17,
                    "managed": True,
                    "legacy_managed": False,
                    "ambiguous": False,
                    "run_pending": False,
                    "kill_pending": False,
                    "pid": 123,
                }
            }

        with mock.patch("concert_launcher.inspection.tmux.list_windows", list_windows):
            result = self.run_async(launcher.status("controller"))

        self.assertEqual(result["robot"]["controller"]["state"], "DEAD")
