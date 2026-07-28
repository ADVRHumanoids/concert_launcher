import io
import unittest

from concert_launcher.output import ConsoleReporter


class OutputTests(unittest.TestCase):
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

    def test_event_includes_dependency_indentation(self):
        stream = io.StringIO()
        reporter = ConsoleReporter(stream=stream, color=False)
        reporter.event("driver", 2, "ready")
        self.assertIn("    └─", stream.getvalue())
