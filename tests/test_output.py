import asyncio
import io
import re
import unittest

from concert_launcher.output import ConsoleReporter
from concert_launcher.output import _PROCESS_STYLES


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

    def test_refresh_header_redraws_from_top_on_interactive_terminal(self):
        stream = TtyStringIO()
        reporter = ConsoleReporter(stream=stream, color=False)
        reporter.refresh_header("Updated: 2026-08-01 14:30:00", redraw=True)

        self.assertTrue(stream.getvalue().startswith("\033[H"))
        self.assertIn("Updated: 2026-08-01 14:30:00", stream.getvalue())

    def test_refresh_header_does_not_redraw_redirected_output(self):
        stream = io.StringIO()
        reporter = ConsoleReporter(stream=stream, color=False)
        reporter.refresh_header("Updated: 2026-08-01 14:30:00", redraw=True)

        self.assertEqual(stream.getvalue(), "Updated: 2026-08-01 14:30:00\n")

    def test_refresh_footer_clears_remainder_only_on_interactive_terminal(self):
        tty_stream = TtyStringIO()
        ConsoleReporter(stream=tty_stream).refresh_footer(redraw=True)
        self.assertEqual(tty_stream.getvalue(), "\033[J")

        plain_stream = io.StringIO()
        ConsoleReporter(stream=plain_stream).refresh_footer(redraw=True)
        self.assertEqual(plain_stream.getvalue(), "")

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

    def test_example_process_colors_do_not_collide_or_use_yellow(self):
        reporter = ConsoleReporter(color=True)
        processes = ("web", "heartbeat_a", "heartbeat_b", "http_probe")
        styles = [reporter.process_style(process) for process in processes]

        self.assertEqual(len(styles), len(set(styles)))
        self.assertNotIn("yellow", styles)
        self.assertNotIn("bright_yellow", styles)
        self.assertNotIn("yellow", _PROCESS_STYLES)
        self.assertNotIn("bright_yellow", _PROCESS_STYLES)

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
