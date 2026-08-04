import asyncio
from types import SimpleNamespace
import unittest

from concert_launcher.main import (
    _clear_watch_screen,
    _fit_watch_frame,
    _paint_watch_frame,
    _render_status_watch_frame,
)
from concert_launcher.output import ConsoleReporter


class RecordingStream:
    def __init__(self, tty=False):
        self.tty = tty
        self.writes = []
        self.flushes = 0

    def isatty(self):
        return self.tty

    def write(self, text):
        self.writes.append(text)

    def flush(self):
        self.flushes += 1


class FakeLauncher:
    def __init__(self):
        self.reporter = ConsoleReporter(stream=RecordingStream(), color=False)

    async def status(self, process, print_to_stdout, raise_on_unavailable):
        self.status_args = (process, print_to_stdout, raise_on_unavailable)
        self.reporter.status_table(
            [
                {
                    "process": "heartbeat_a",
                    "session": "concert_examples",
                    "machine": "tester@127.0.0.1:2222",
                    "state": "RUNNING",
                    "pid": 123,
                    "exitstatus": "-",
                }
            ]
        )

    async def pstree(self, process):
        self.pstree_process = process
        self.reporter.event(process or "all", 0, "process tree:\n  root")


class MainStatusWatchTests(unittest.TestCase):
    def test_status_watch_frame_is_buffered_and_restores_reporter(self):
        launcher = FakeLauncher()
        original_reporter = launcher.reporter
        args = SimpleNamespace(process="heartbeat_a", pstree=False)

        frame = asyncio.run(
            _render_status_watch_frame(
                launcher,
                args,
                "2026-08-01 14:30:00",
            )
        )

        self.assertIs(launcher.reporter, original_reporter)
        self.assertEqual(launcher.status_args, ("heartbeat_a", True, False))
        self.assertIn("Updated: 2026-08-01 14:30:00", frame)
        self.assertIn("PROCESS", frame)
        self.assertIn("heartbeat_a", frame)
        self.assertEqual(original_reporter.stream.writes, [])

    def test_paint_watch_frame_writes_once_to_tty(self):
        stream = RecordingStream(tty=True)
        reporter = ConsoleReporter(stream=stream, color=False)

        _paint_watch_frame(reporter, "Updated\nPROCESS\n")

        self.assertEqual(stream.writes, ["\033[HUpdated\nPROCESS\033[J"])
        self.assertEqual(stream.flushes, 1)

    def test_paint_watch_frame_does_not_add_ansi_when_redirected(self):
        stream = RecordingStream(tty=False)
        reporter = ConsoleReporter(stream=stream, color=False)

        _paint_watch_frame(reporter, "Updated\nPROCESS\n")

        self.assertEqual(stream.writes, ["Updated\nPROCESS\n"])
        self.assertEqual(stream.flushes, 1)

    def test_clear_watch_screen_only_clears_tty(self):
        tty_stream = RecordingStream(tty=True)
        _clear_watch_screen(ConsoleReporter(stream=tty_stream, color=False))
        self.assertEqual(tty_stream.writes, ["\033[2J\033[H"])
        self.assertEqual(tty_stream.flushes, 1)

        plain_stream = RecordingStream(tty=False)
        _clear_watch_screen(ConsoleReporter(stream=plain_stream, color=False))
        self.assertEqual(plain_stream.writes, [])
        self.assertEqual(plain_stream.flushes, 0)

    def test_fit_watch_frame_keeps_top_lines_visible_when_truncated(self):
        frame = "Updated\nPROCESS\n-------\none\ntwo\nthree\n"

        fitted = _fit_watch_frame(frame, rows=4)

        self.assertEqual(
            fitted,
            "Updated\nPROCESS\n-------\n... truncated 3 lines ...",
        )
        self.assertFalse(fitted.endswith("\n"))
