import os
import unittest
from unittest import mock

from concert_launcher.output import cli_color_enabled


class FakeStream:
    def __init__(self, tty):
        self.tty = tty

    def isatty(self):
        return self.tty


class CliColorTests(unittest.TestCase):
    def test_cli_enables_color_for_interactive_terminal(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(cli_color_enabled(FakeStream(True)))

    def test_cli_disables_color_for_redirected_output(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(cli_color_enabled(FakeStream(False)))

    def test_cli_honors_no_color(self):
        with mock.patch.dict(os.environ, {"NO_COLOR": ""}, clear=True):
            self.assertFalse(cli_color_enabled(FakeStream(True)))

    def test_cli_disables_color_for_dumb_terminal(self):
        with mock.patch.dict(os.environ, {"TERM": "dumb"}, clear=True):
            self.assertFalse(cli_color_enabled(FakeStream(True)))


if __name__ == "__main__":
    unittest.main()
