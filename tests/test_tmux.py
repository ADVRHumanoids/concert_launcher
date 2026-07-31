import asyncio
import unittest

from concert_launcher import tmux


class TmuxTests(unittest.TestCase):
    def run_async(self, coroutine):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coroutine)
        finally:
            loop.close()

    def test_list_windows_preserves_tmux_format_and_exit_status(self):
        commands = []
        original_run_cmd = tmux.run_cmd

        async def fake_run_cmd(connection, command, throw_on_failure=False):
            del connection, throw_on_failure
            commands.append(command)
            if command.startswith("tmux list-w"):
                return 0, "robot\tprocess\t123\t1\texit=17", ""
            return 1, "", ""

        async def scenario():
            tmux.run_cmd = fake_run_cmd
            try:
                result = await tmux.list_windows(None, "robot")
            finally:
                tmux.run_cmd = original_run_cmd

            self.assertIn("#{session_name}", commands[0])
            self.assertIn("exit=#{pane_dead_status}", commands[0])
            self.assertEqual(result["process"]["pid"], 123)
            self.assertTrue(result["process"]["dead"])
            self.assertEqual(result["process"]["exitstatus"], 17)

        self.run_async(scenario())

    def test_list_windows_keeps_empty_live_exit_status_column(self):
        original_run_cmd = tmux.run_cmd

        async def fake_run_cmd(connection, command, throw_on_failure=False):
            del connection, throw_on_failure
            if command.startswith("tmux list-w"):
                return 0, "robot\tprocess\t123\t0\texit=", ""
            return 1, "", ""

        async def scenario():
            tmux.run_cmd = fake_run_cmd
            try:
                result = await tmux.list_windows(None, "robot")
            finally:
                tmux.run_cmd = original_run_cmd

            self.assertFalse(result["process"]["dead"])
            self.assertEqual(result["process"]["exitstatus"], 0)

        self.run_async(scenario())
