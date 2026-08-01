import asyncio
import io
import re
import unittest

from concert_launcher.output import ConsoleReporter


class TtyStringIO(io.StringIO):
    def isatty(self):
        return True


class OutputTests(unittest.TestCase):
    def test_reporter_is_plain_by_default_even_for_tty_stream(self):
        stream = TtyStringIO()
        reporter = ConsoleReporter(stream=stream)
        reporter.event("controller", 0, "ready")
        self.assertNotIn("\033", stream.getvalue())

    def test_status_table_is_aligned_and_readable_without_color(self):
        stream = io.StringIO()
        reporter = ConsoleReporter(stream=stream, color=False)
        reporter.status_table(
            [
                {
                    "process": "controller",
                    "session": "robot",
                    "machine": "operator@robot-pc",
                    "state": "RUNNING",
                    "pid": 123,
                    "exitstatus": 0,
                },
                {
                    "process": "camera",
                    "session": "robot",
                    "machine": "operator@vision-pc",
                    "state": "UNAVAILABLE",
                    "pid": "-",
                    "exitstatus": "-",
                },
            ]
        )
        output = stream.getvalue()
        self.assertIn("PROCESS", output)
        self.assertIn("controller", output)
        self.assertIn("UNAVAILABLE", output)
        self.assertNotIn("\033", output)

    def test_watch_colors_only_the_process_label(self):
        stream = io.StringIO()
        reporter = ConsoleReporter(stream=stream, color=True)
        asyncio.run(reporter.watch_printer("controller")("body remains plain\n"))
        output = stream.getvalue()
        self.assertIn("\033", output)
        self.assertTrue(output.endswith("\033[0m body remains plain\n"))
        self.assertNotIn("\033", output.split("\033[0m ", 1)[1])

    def test_process_colors_are_stable_and_can_differentiate_names(self):
        reporter = ConsoleReporter(color=True)
        self.assertEqual(
            reporter.process_style("controller"),
            reporter.process_style("controller"),
        )
        self.assertNotEqual(
            reporter.process_style("controller"),
            reporter.process_style("camera"),
        )

    def test_status_uses_distinct_state_colors(self):
        stream = io.StringIO()
        reporter = ConsoleReporter(stream=stream, color=True)
        reporter.status_table(
            [
                {"process": "a", "state": "RUNNING"},
                {"process": "b", "state": "DEAD"},
                {"process": "c", "state": "UNAVAILABLE"},
                {"process": "d", "state": "CONFLICT"},
                {"process": "e", "state": "STOPPED"},
            ]
        )
        output = stream.getvalue()
        prefixes = {}
        for state in ("RUNNING", "DEAD", "UNAVAILABLE", "CONFLICT", "STOPPED"):
            match = re.search(r"((?:\033\[[0-9;]*m)+)" + state, output)
            self.assertIsNotNone(match, state)
            prefixes[state] = match.group(1)
        self.assertEqual(len(set(prefixes.values())), len(prefixes))

    def test_event_includes_dependency_indentation(self):
        stream = io.StringIO()
        reporter = ConsoleReporter(stream=stream, color=False)
        reporter.event("driver", 2, "ready")
        self.assertIn("    └─", stream.getvalue())
