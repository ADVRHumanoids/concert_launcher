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

    def status_for_exit(self, exitstatus):
        config = {
            "context": {"session": "robot"},
            "controller": {"cmd": "controller"},
        }
        launcher = Launcher(config, connection_manager=LocalManager())

        async def list_windows(_connection, _session):
            return {
                "controller": {
                    "dead": True,
                    "exitstatus": exitstatus,
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

        return result["robot"]["controller"]

    def test_dead_pane_with_zero_exit_is_stopped(self):
        entry = self.status_for_exit(0)
        self.assertEqual(entry["state"], "STOPPED")
        self.assertEqual(entry["exitstatus"], 0)

    def test_dead_pane_with_expected_signal_exit_is_stopped(self):
        for exitstatus in (130, 131, 143):
            with self.subTest(exitstatus=exitstatus):
                entry = self.status_for_exit(exitstatus)
                self.assertEqual(entry["state"], "STOPPED")
                self.assertEqual(entry["exitstatus"], exitstatus)

    def test_dead_pane_with_other_nonzero_exit_is_dead(self):
        entry = self.status_for_exit(17)
        self.assertEqual(entry["state"], "DEAD")
        self.assertEqual(entry["exitstatus"], 17)
