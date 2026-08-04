import asyncio
import unittest
from unittest import mock

from concert_launcher import resources


class ResourceTests(unittest.TestCase):
    def run_async(self, coroutine):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coroutine)
        finally:
            loop.close()

    def test_ensure_resources_refreshes_all_helpers(self):
        copied = []
        commands = []

        async def putfile(connection, local_path, remote_path):
            copied.append((connection, local_path, remote_path))

        async def run_cmd(connection, command, **kwargs):
            del kwargs
            commands.append((connection, command))
            return 0, "", ""

        with mock.patch.object(resources.remote, "putfile", putfile):
            with mock.patch.object(resources.remote, "run_cmd", run_cmd):
                self.run_async(resources.ensure_resources("ssh"))

        self.assertEqual(len(copied), len(resources.RESOURCE_FILES))
        self.assertEqual(
            [item[1].split("/")[-1] for item in copied],
            list(resources.RESOURCE_FILES),
        )
        self.assertTrue(commands)
        self.assertIn("chmod 755", commands[-1][1])
