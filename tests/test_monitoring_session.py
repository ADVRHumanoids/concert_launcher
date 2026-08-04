import os
from types import SimpleNamespace
import unittest
from unittest import mock

from concert_launcher import monitoring_session
from concert_launcher.monitoring_session import (
    _create_monitoring_session_non_reentrant,
    _remote_attach_command,
    _reset_monitor_session,
    _ssh_monitor_command,
)


class MonitoringSessionTests(unittest.TestCase):
    def test_remote_attach_command_targets_configured_session_and_process(self):
        command = _remote_attach_command("concert_examples", "web")

        self.assertIn("tmux has-session -t concert_examples:web", command)
        self.assertIn("tmux attach -t concert_examples:web", command)
        self.assertNotIn("web:web", command)

    def test_ssh_monitor_command_supports_host_port_and_generated_auth_files(self):
        with mock.patch.dict(
            os.environ,
            {
                "CONCERT_LAUNCHER_SSH_KEY": "/tmp/lab key",
                "CONCERT_LAUNCHER_KNOWN_HOSTS": "/tmp/known hosts",
            },
        ):
            command = _ssh_monitor_command(
                "tester@127.0.0.1:2222",
                "tmux attach -t concert_examples:web",
            )

        self.assertIn("ssh -tt", command)
        self.assertIn("-p 2222", command)
        self.assertIn("-i '/tmp/lab key'", command)
        self.assertIn("'UserKnownHostsFile=/tmp/known hosts'", command)
        self.assertIn("tester@127.0.0.1", command)
        self.assertNotIn("tester@127.0.0.1:2222", command)

    def test_split_uses_stable_pane_ids(self):
        commands = []

        async def run_cmd(_connection, command, **kwargs):
            del kwargs
            commands.append(command)
            if "has-session" in command:
                return 1, "", ""
            if "display-message" in command:
                return 0, "%1\n", ""
            if "split-window" in command:
                return 0, "%2\n", ""
            return 0, "", ""

        first = SimpleNamespace(
            persistent=True,
            session="concert_examples",
            machine=None,
        )
        second = SimpleNamespace(
            persistent=True,
            session="concert_examples",
            machine=None,
        )

        async def scenario():
            monitoring_session.pkg_already_processed.clear()
            monitoring_session.num_cols = 3
            monitoring_session.pane_to_split = 0
            monitoring_session.num_rows = 1
            monitoring_session.num_panes = 0
            monitoring_session.pane_targets = []
            await _create_monitoring_session_non_reentrant(
                first,
                "web",
                1,
                "concert_examples_mon",
            )
            await _create_monitoring_session_non_reentrant(
                second,
                "heartbeat_a",
                1,
                "concert_examples_mon",
            )

        with mock.patch.object(monitoring_session.remote, "run_cmd", run_cmd):
            import asyncio

            asyncio.run(scenario())

        split_commands = [command for command in commands if "split-window" in command]
        self.assertEqual(len(split_commands), 1)
        self.assertIn("-t %1", split_commands[0])
        self.assertNotIn("concert_examples_mon:concert_examples.0", split_commands[0])

    def test_top_level_creation_kills_stale_monitor_session_before_rebuild(self):
        commands = []

        async def run_cmd(_connection, command, **kwargs):
            del kwargs
            commands.append(command)
            return 0, "", ""

        with mock.patch.object(monitoring_session.remote, "run_cmd", run_cmd):
            import asyncio

            asyncio.run(_reset_monitor_session("concert_examples_mon"))

        self.assertIn(
            "tmux kill-session -t concert_examples_mon",
            commands,
        )
