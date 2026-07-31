"""Local and AsyncSSH command transport primitives."""

import asyncio
import logging
import shlex
import shutil

import asyncssh

from .errors import CommandError, RemoteConnectionError

logger = logging.getLogger(__name__)


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
    cmd_real = "bash -ic {}".format(shlex.quote(cmd)) if interactive else cmd
    logger.debug("running on %s: %s", connection_machine(connection), cmd_real)

    try:
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
    del interactive, throw_on_failure
    try:
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
