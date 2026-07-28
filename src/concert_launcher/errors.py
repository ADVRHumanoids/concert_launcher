"""Public exception types raised by Concert Launcher."""


class LauncherError(RuntimeError):
    """Base class for recoverable launcher failures."""


class ConfigurationError(LauncherError):
    """The launcher configuration is invalid or incomplete."""


class CommandError(LauncherError):
    """A local or remote command returned a non-zero exit status."""

    def __init__(self, command, returncode=None, stderr=""):
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        detail = "command failed"
        if returncode is not None:
            detail += " with exit code {}".format(returncode)
        if stderr:
            detail += ": {}".format(stderr.strip())
        super().__init__(detail)


class RemoteConnectionError(LauncherError):
    """A retryable SSH transport failure.

    Attributes:
        machine: The configured ``user@host`` target.
        operation: Human-readable operation which failed.
        retryable: Always true for this exception type. Callers can use this
            flag without importing AsyncSSH-specific exception classes.
        cause: The original exception raised by AsyncSSH or the socket layer.
    """

    retryable = True

    def __init__(self, machine, operation, cause):
        self.machine = machine
        self.operation = operation
        self.cause = cause
        message = "SSH operation {!r} failed for {}: {}".format(
            operation, machine, cause
        )
        super().__init__(message)


class ProcessError(LauncherError):
    """A managed process could not be started, stopped, or inspected."""
