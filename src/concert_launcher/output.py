"""Human-friendly terminal formatting with no mandatory UI dependency."""

import functools
import sys


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
        if not self.color:
            return text
        prefix = "".join(_ANSI[style] for style in styles)
        return prefix + text + _ANSI["reset"]

    @staticmethod
    def _event_style(text):
        lowered = text.lower()
        if any(token in lowered for token in ("failed", "error", "unavailable")):
            return "✗", "red"
        if any(token in lowered for token in ("ready", "success", "killed")):
            return "✓", "green"
        if any(token in lowered for token in ("waiting", "checking", "opening")):
            return "…", "yellow"
        return "•", "cyan"

    def event(self, process, level, text):
        marker, style = self._event_style(text)
        branch = "  " * level + ("└─ " if level else "")
        label = self._style("[{}]".format(process), "bold")
        marker = self._style("{:>2}".format(marker), style)
        print("{}{} {} {}".format(branch, marker, label, text), file=self.stream)

    def status_table(self, rows):
        headers = ("PROCESS", "SESSION", "MACHINE", "STATE", "PID", "EXIT")
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
