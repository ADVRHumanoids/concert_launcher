"""Render readable events and status tables without a UI dependency.

The reporter keeps formatting decisions outside lifecycle code, supports plain
streams for libraries and tests, and enables ANSI styling only for terminals.
"""

import functools
import sys


# A deliberately small palette keeps output predictable across terminals.
_ANSI = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
}


class ConsoleReporter:
    """Render process events and status tables consistently."""

    def __init__(self, stream=None, color=None):
        self.stream = stream or sys.stdout
        self.color = self.stream.isatty() if color is None else bool(color)

    def _style(self, text, *styles):
        """Apply ANSI styles only when color output is enabled."""
        if not self.color:
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

    def event(self, process, level, text):
        """Render one graph-aware lifecycle event."""
        marker, style = self._event_style(text)
        branch = "  " * level + ("└─ " if level else "")
        label = self._style("[{}]".format(process), "bold")
        marker = self._style("{:>2}".format(marker), style)
        print("{}{} {} {}".format(branch, marker, label, text), file=self.stream)

    def status_table(self, rows):
        """Normalize rows, calculate widths, and render an aligned table."""
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

        def format_row(values):
            return "  ".join(value.ljust(width) for value, width in zip(values, widths))

        print(self._style(format_row(headers), "bold", "cyan"), file=self.stream)
        print(self._style("  ".join("-" * width for width in widths), "dim"), file=self.stream)

        # Color the full row by state so the table remains legible even when a
        # terminal does not align colored substrings consistently.
        for row in normalized:
            rendered = format_row(row)
            state = row[3]
            if state == "RUNNING":
                rendered = self._style(rendered, "green")
            elif state in ("DEAD", "UNAVAILABLE"):
                rendered = self._style(rendered, "red")
            elif state in ("STARTING", "STOPPING"):
                rendered = self._style(rendered, "yellow")
            print(rendered, file=self.stream)


# Historical printing calls delegate to one default reporter.
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
