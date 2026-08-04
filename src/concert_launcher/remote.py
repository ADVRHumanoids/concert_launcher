"""Execute commands and copy files over local or AsyncSSH transports.

Every higher-level module uses these primitives, which keeps local/remote
behavior aligned and converts transport failures into ``RemoteConnectionError``.
"""

import asyncio
import logging
import shlex
import shutil

import asyncssh

from .errors import CommandError, RemoteConnectionError

logger = logging.getLogger(__name__)


# Error messages should identify the host even when an AsyncSSH object exposes
# its connection metadata through private attributes.
def connection_machine(connection):
    if connection is None:
        return "local"
    user = getattr(connection, "_username", None) or getattr(
        connection, "username", None
    )
    host = getattr(connection, "_host", None) or getattr(connection, "host", None)
    if user and host:
        return "{}@{}".format(user, host)
    return str(host or "remote host")


# Resource deployment uses a normal filesystem copy locally and SCP remotely.
async def putfile(connection, local_path, remote_path):
    if connection is None:
        shutil.copy(local_path, remote_path)
        return
    try:
        await asyncssh.scp(local_path, (connection, remote_path))
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise RemoteConnectionError(
            connection_machine(connection),
            "copy {} to {}".format(local_path, remote_path),
            exc,
        ) from exc


async def run_cmd(
    connection,
    cmd,
    timeout=None,
    interactive=False,
    throw_on_failure=True,
):
    """Run one finite command and return ``(code, stdout, stderr)``."""
    # Interactive commands use a login-style shell. A PTY is requested only
    # for this path because forcing one on the shared connection breaks SCP.
    cmd_real = "bash -ic {}".format(shlex.quote(cmd)) if interactive else cmd
    logger.debug("running on %s: %s", connection_machine(connection), cmd_real)

    try:
        # Local and SSH execution intentionally converge on the same normalized
        # return tuple before error policy is applied below.
        if connection is None:
            proc = await asyncio.create_subprocess_shell(
                cmd_real,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")
            returncode = proc.returncode
        else:
            run_options = {"check": False, "timeout": timeout}
            if interactive:
                run_options["request_pty"] = "force"
            result = await connection.run(cmd_real, **run_options)
            returncode = result.returncode
            stdout = result.stdout
            stderr = result.stderr
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError as exc:
        # Remote timeouts are recoverable transport failures; local timeouts
        # remain command failures because no connection can be refreshed.
        if connection is not None:
            raise RemoteConnectionError(
                connection_machine(connection),
                "run command {!r}".format(cmd),
                exc,
            ) from exc
        raise CommandError(cmd, stderr="timed out") from exc
    except Exception as exc:
        if connection is not None:
            raise RemoteConnectionError(
                connection_machine(connection),
                "run command {!r}".format(cmd),
                exc,
            ) from exc
        raise

    # Normalize AsyncSSH and subprocess output before deciding whether a
    # non-zero return code should be raised or returned to the caller.
    stdout = (stdout or "").strip()
    stderr = (stderr or "").strip()
    if throw_on_failure and returncode != 0:
        raise CommandError(cmd, returncode, stderr)
    return returncode, stdout, stderr


async def watch_process(
    connection,
    cmd,
    stdout_coro,
    interactive=False,
    throw_on_failure=True,
):
    """Stream stdout lines until the command ends or the transport fails."""
    del interactive, throw_on_failure
    try:
        # Keep the stream object alive while forwarding each line to the
        # caller-provided coroutine. The higher layer owns cancellation.
        if connection is None:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL,
            )
            decode = True
        else:
            proc = await connection.create_process(cmd)
            decode = False

        while True:
            line = await proc.stdout.readline()
            if not line:
                return
            if decode:
                line = line.decode(errors="replace")
            await stdout_coro(line)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if connection is not None:
            raise RemoteConnectionError(
                connection_machine(connection), "watch process output", exc
            ) from exc
        raise
