"""Render readable events, watches, and status tables.

The reporter is deliberately plain by default so library users never receive
ANSI escapes unexpectedly. The CLI opts into color explicitly when stdout is a
compatible terminal.
"""

import functools
import os
import sys
import zlib


# A compact ANSI palette keeps output predictable without adding a UI package.
_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "bright_red": "\033[91m",
    "bright_green": "\033[92m",
    "bright_yellow": "\033[93m",
    "bright_blue": "\033[94m",
    "bright_magenta": "\033[95m",
    "bright_cyan": "\033[96m",
}

# Process colors are stable across runs; Python's randomized hash is avoided.
_PROCESS_STYLES = (
    "cyan",
    "magenta",
    "blue",
    "green",
    "yellow",
    "bright_cyan",
    "bright_magenta",
    "bright_blue",
    "bright_green",
    "bright_yellow",
)

# State colors are intentionally distinct so a status table can be scanned
# before the text itself is read.
_STATE_STYLES = {
    "RUNNING": ("bright_green",),
    "STARTING": ("yellow",),
    "STOPPING": ("bright_yellow",),
    "STOPPED": ("dim",),
    "DEAD": ("red",),
    "UNAVAILABLE": ("bright_red", "bold"),
    "CONFLICT": ("bright_magenta", "bold"),
    "UNKNOWN": ("yellow",),
}


def cli_color_enabled(stream, environ=None):
    """Return whether CLI output should use ANSI styling."""
    environment = os.environ if environ is None else environ
    is_tty = getattr(stream, "isatty", lambda: False)()
    return (
        is_tty
        and "NO_COLOR" not in environment
        and environment.get("TERM", "") != "dumb"
    )


class ConsoleReporter:
    """Render process output consistently for plain or colored streams."""

    def __init__(self, stream=None, color=False):
        self.stream = stream or sys.stdout
        # Color is opt-in. This keeps the reusable API ASCII/ANSI-free.
        self.color = bool(color)

    def _style(self, text, *styles):
        """Apply ANSI styles only when color output is enabled."""
        if not self.color or not styles:
            return text
        prefix = "".join(_ANSI[style] for style in styles)
        return prefix + text + _ANSI["reset"]

    @staticmethod
    def _event_style(text):
        """Map common lifecycle words to a marker and semantic color."""
        lowered = text.lower()
        if any(token in lowered for token in ("failed", "error", "unavailable")):
            return "✗", "red"
        if any(token in lowered for token in ("ready", "success", "killed")):
            return "✓", "green"
        if any(token in lowered for token in ("waiting", "checking", "opening")):
            return "…", "yellow"
        return "•", "cyan"

    @staticmethod
    def process_style(process):
        """Return a deterministic palette entry for a process name."""
        checksum = zlib.crc32(str(process).encode("utf-8"))
        return _PROCESS_STYLES[checksum % len(_PROCESS_STYLES)]

    def process_label(self, process):
        """Render one stable, colored process label."""
        label = "[{}]".format(process)
        return self._style(label, "bold", self.process_style(process))

    def event(self, process, level, text):
        """Render one graph-aware lifecycle event."""
        marker, style = self._event_style(text)
        branch = "  " * level + ("└─ " if level else "")
        marker = self._style("{:>2}".format(marker), style)
        label = self.process_label(process)
        # Marker and label reset independently, leaving message text untouched.
        print("{}{} {} {}".format(branch, marker, label, text), file=self.stream)

    def watch_printer(self, process):
        """Create an async line printer for ``watch`` output."""
        label = self.process_label(process)

        async def print_line(line):
            # Resetting after the label prevents its color leaking into output.
            print("{} {}".format(label, line), end="", file=self.stream)

        return print_line

    def status_table(self, rows):
        """Render aligned rows with process and lifecycle-state coloring."""
        headers = ("PROCESS", "SESSION", "MACHINE", "STATE", "PID", "EXIT")

        # Convert every field once so width calculation and rendering share the
        # exact same values.
        normalized = []
        for row in rows:
            normalized.append(tuple(str(row.get(key, "-")) for key in (
                "process", "session", "machine", "state", "pid", "exitstatus"
            )))

        widths = [len(value) for value in headers]
        for row in normalized:
            widths = [max(width, len(value)) for width, value in zip(widths, row)]

        def padded(values):
            return [value.ljust(width) for value, width in zip(values, widths)]

        print(
            self._style("  ".join(padded(headers)), "bold", "cyan"),
            file=self.stream,
        )
        print(
            self._style("  ".join("-" * width for width in widths), "dim"),
            file=self.stream,
        )

        # Only the process and state cells are colored. Identifiers, PIDs, and
        # exit values remain in the terminal's default foreground color.
        for row in normalized:
            cells = padded(row)
            cells[0] = self._style(cells[0], self.process_style(row[0]))
            state_styles = _STATE_STYLES.get(row[3], _STATE_STYLES["UNKNOWN"])
            cells[3] = self._style(cells[3], *state_styles)
            print("  ".join(cells), file=self.stream)


# Historical API calls remain plain unless callers inject a colored reporter.
_default_reporter = ConsoleReporter()


class ProgressReporter:
    """Backward-compatible adapter for the historical printing API."""

    @classmethod
    def print(cls, pkg, level, text, **kwargs):
        del kwargs
        _default_reporter.event(pkg, level, text)

    @classmethod
    def get_print_fn(cls, pkg, level):
        return functools.partial(cls.print, pkg, level)
