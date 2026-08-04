import asyncio
import unittest

from concert_launcher import tmux
from concert_launcher.errors import ProcessError


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
                return (
                    0,
                    "robot\tprocess\t@1\t123\t1\texit=17\tmanaged=1\t"
                    "/tmp/concert_launcher_wrapper.bash process cmd",
                    "",
                )
            if command.startswith("test -f"):
                return 1, "", ""
            return 0, "", ""

        async def scenario():
            tmux.run_cmd = fake_run_cmd
            try:
                result = await tmux.list_windows(None, "robot")
            finally:
                tmux.run_cmd = original_run_cmd

            self.assertIn("#{session_name}", commands[0])
            self.assertIn("exit=#{pane_dead_status}", commands[0])
            self.assertIn("managed=#{@concert_launcher_managed}", commands[0])
            self.assertIn("#{pane_start_command}", commands[0])
            self.assertEqual(result["process"]["id"], "@1")
            self.assertEqual(result["process"]["pid"], 123)
            self.assertTrue(result["process"]["dead"])
            self.assertTrue(result["process"]["managed"])
            self.assertFalse(result["process"]["legacy_managed"])
            self.assertEqual(result["process"]["exitstatus"], 17)

        self.run_async(scenario())

    def test_list_windows_keeps_empty_live_exit_status_column(self):
        original_run_cmd = tmux.run_cmd

        async def fake_run_cmd(connection, command, throw_on_failure=False):
            del connection, throw_on_failure
            if command.startswith("tmux list-w"):
                return (
                    0,
                    "robot\tprocess\t@1\t123\t0\texit=\tmanaged=1\t"
                    "/tmp/concert_launcher_wrapper.bash process cmd",
                    "",
                )
            if command.startswith("test -f"):
                return 1, "", ""
            return 0, "", ""

        async def scenario():
            tmux.run_cmd = fake_run_cmd
            try:
                result = await tmux.list_windows(None, "robot")
            finally:
                tmux.run_cmd = original_run_cmd

            self.assertFalse(result["process"]["dead"])
            self.assertEqual(result["process"]["exitstatus"], 0)

        self.run_async(scenario())

    def test_legacy_wrapper_window_remains_managed_without_tag(self):
        original_run_cmd = tmux.run_cmd

        async def fake_run_cmd(connection, command, throw_on_failure=False):
            del connection, throw_on_failure
            if command.startswith("tmux list-w"):
                return (
                    0,
                    "robot\tprocess\t@1\t123\t0\texit=\tmanaged=\t"
                    "/tmp/concert_launcher_wrapper.bash process cmd",
                    "",
                )
            if command.startswith("test -f"):
                return 1, "", ""
            return 0, "", ""

        async def scenario():
            tmux.run_cmd = fake_run_cmd
            try:
                result = await tmux.list_windows(None, "robot")
            finally:
                tmux.run_cmd = original_run_cmd

            self.assertTrue(result["process"]["managed"])
            self.assertTrue(result["process"]["legacy_managed"])

        self.run_async(scenario())

    def test_list_windows_marks_managed_and_ignores_foreign_markers(self):
        commands = []
        original_run_cmd = tmux.run_cmd

        async def fake_run_cmd(connection, command, throw_on_failure=False):
            del connection, throw_on_failure
            commands.append(command)
            if command.startswith("tmux list-w"):
                return (
                    0,
                    "robot\tmanaged\t@1\t123\t0\texit=\tmanaged=1\t"
                    "/tmp/concert_launcher_wrapper.bash managed cmd\n"
                    "robot\tforeign;touch /tmp/pwned\t@2\t124\t0\texit=\t"
                    "managed=\tsleep 1000",
                    "",
                )
            if command.startswith("test -f"):
                return 1, "", ""
            return 0, "", ""

        async def scenario():
            tmux.run_cmd = fake_run_cmd
            try:
                result = await tmux.list_windows(None, "robot")
            finally:
                tmux.run_cmd = original_run_cmd

            self.assertTrue(result["managed"]["managed"])
            self.assertFalse(result["foreign;touch /tmp/pwned"]["managed"])
            marker_commands = [c for c in commands if c.startswith("test -f")]
            self.assertEqual(len(marker_commands), 2)
            self.assertTrue(all("managed" in c for c in marker_commands))
            self.assertTrue(all("pwned" not in c for c in marker_commands))

        self.run_async(scenario())

    def test_duplicate_window_names_are_ambiguous(self):
        original_run_cmd = tmux.run_cmd

        async def fake_run_cmd(connection, command, throw_on_failure=False):
            del connection, throw_on_failure
            if command.startswith("tmux list-w"):
                return (
                    0,
                    "robot\tprocess\t@1\t123\t0\texit=\tmanaged=1\t"
                    "/tmp/concert_launcher_wrapper.bash process cmd\n"
                    "robot\tprocess\t@2\t124\t0\texit=\tmanaged=\tsleep 1000",
                    "",
                )
            if command.startswith("test -f"):
                return 1, "", ""
            return 0, "", ""

        async def scenario():
            tmux.run_cmd = fake_run_cmd
            try:
                result = await tmux.list_windows(None, "robot")
            finally:
                tmux.run_cmd = original_run_cmd

            info = result["process"]
            self.assertTrue(info["ambiguous"])
            self.assertFalse(info["managed"])
            self.assertEqual(info["window_ids"], ["@1", "@2"])
            with self.assertRaises(ProcessError):
                tmux.require_managed_window("robot", "process", info)

        self.run_async(scenario())

    def test_spawn_refuses_unmanaged_name_collision(self):
        commands = []
        original_run_cmd = tmux.run_cmd

        async def fake_run_cmd(connection, command, throw_on_failure=False):
            del connection, throw_on_failure
            commands.append(command)
            if command.startswith("tmux list-w"):
                return (
                    0,
                    "robot\tprocess\t@9\t321\t0\texit=\tmanaged=\tsleep 1000",
                    "",
                )
            return 0, "", ""

        async def scenario():
            tmux.run_cmd = fake_run_cmd
            try:
                with self.assertRaises(ProcessError):
                    await tmux.spawn_window(None, "robot", "process", "echo hi")
            finally:
                tmux.run_cmd = original_run_cmd

            self.assertFalse(any("respawn-window" in c for c in commands))
            self.assertFalse(any("send-keys" in c for c in commands))

        self.run_async(scenario())

    def test_spawn_tags_new_window_as_managed(self):
        commands = []
        original_run_cmd = tmux.run_cmd

        async def fake_run_cmd(connection, command, throw_on_failure=False):
            del connection, throw_on_failure
            commands.append(command)
            if command.startswith("tmux list-w"):
                return (
                    0,
                    "robot\tforeign\t@1\t123\t0\texit=\tmanaged=\tsleep 1000",
                    "",
                )
            return 0, "", ""

        async def scenario():
            tmux.run_cmd = fake_run_cmd
            try:
                await tmux.spawn_window(None, "robot", "process", "echo hi")
            finally:
                tmux.run_cmd = original_run_cmd

            combined = "\n".join(commands)
            self.assertIn("new-window", combined)
            self.assertIn(tmux.MANAGED_OPTION, combined)

        self.run_async(scenario())
