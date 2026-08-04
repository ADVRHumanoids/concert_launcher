"""Own AsyncSSH connection reuse, validation, and recovery.

Callers ask for a machine by name and receive either a healthy SSH connection
or ``None`` for local execution. This module is the only place which caches
connections, so stale transports and reconnect behavior remain consistent.
"""

import asyncio
import logging
import os

import asyncssh

from .errors import ConfigurationError, RemoteConnectionError

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Cache healthy SSH connections and make failures explicit.

    A failed connection is never cached. Closed cached connections are removed
    automatically and recreated on the next ``get()`` call.
    """

    def __init__(self, connect=None):
        self._connect = connect or asyncssh.connect
        self._connections = {}
        self._lock = None
        self._lock_loop = None

    # Serialize cache changes so concurrent graph nodes do not open duplicate
    # connections to the same machine.
    def _get_lock(self):
        loop = asyncio.get_event_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    # Machine validation belongs here because every remote operation flows
    # through this manager before an AsyncSSH connection is created.
    @staticmethod
    def _parse_machine(machine):
        if not machine or "@" not in machine:
            raise ConfigurationError(
                "remote machine must use the 'user@host' or 'user@host:port' form: "
                "{!r}".format(machine)
            )
        user, host = machine.split("@", 1)
        if not user or not host:
            raise ConfigurationError(
                "remote machine must use the 'user@host' or 'user@host:port' form: "
                "{!r}".format(machine)
            )
        port = None
        if host.count(":") == 1:
            host_part, port_part = host.rsplit(":", 1)
            if not port_part:
                raise ConfigurationError(
                    "remote machine port must be numeric: {!r}".format(machine)
                )
            try:
                port = int(port_part)
            except ValueError as exc:
                raise ConfigurationError(
                    "remote machine port must be numeric: {!r}".format(machine)
                ) from exc
            if not host_part:
                raise ConfigurationError(
                    "remote machine must include a host: {!r}".format(machine)
                )
            host = host_part
        return user, host, port

    @staticmethod
    def _connect_options():
        options = {}
        key_path = os.environ.get("CONCERT_LAUNCHER_SSH_KEY")
        known_hosts = os.environ.get("CONCERT_LAUNCHER_KNOWN_HOSTS")
        if key_path:
            options["client_keys"] = [key_path]
        if known_hosts:
            options["known_hosts"] = known_hosts
        return options

    # AsyncSSH versions expose slightly different health helpers. Treat any
    # failing health check as closed rather than risking reuse of a bad socket.
    @staticmethod
    def _is_closed(connection):
        for attribute in ("is_closed", "is_closing"):
            check = getattr(connection, attribute, None)
            if callable(check):
                try:
                    if check():
                        return True
                except Exception:
                    return True
        return False

    async def get(self, machine):
        """Return a live connection, or ``None`` for local execution."""
        if machine in (None, "local"):
            return None

        async with self._get_lock():
            # Fast path: reuse a cached connection only after confirming that
            # its transport is still open.
            cached = self._connections.get(machine)
            if cached is not None and not self._is_closed(cached):
                return cached

            # Slow path: remove a stale cache entry before opening a fresh SSH
            # transport. Failed attempts never enter the cache.
            if cached is not None:
                await self._close_connection(cached)
                self._connections.pop(machine, None)

            user, host, port = self._parse_machine(machine)
            options = self._connect_options()
            if port is not None:
                options["port"] = port
            try:
                logger.info("opening SSH connection to %s", machine)
                connection = await self._connect(
                    host=host,
                    username=user,
                    **options,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise RemoteConnectionError(machine, "connect", exc) from exc

            # Defensive checks keep ``None`` reserved exclusively for local
            # execution and prevent a closed connection from being cached.
            if connection is None:
                raise RemoteConnectionError(
                    machine, "connect", RuntimeError("AsyncSSH returned no connection")
                )
            if self._is_closed(connection):
                await self._close_connection(connection)
                raise RemoteConnectionError(
                    machine, "connect", RuntimeError("AsyncSSH returned a closed connection")
                )

            self._connections[machine] = connection
            return connection

    async def invalidate(self, machine):
        """Remove and close a cached connection after a transport failure."""
        if machine in (None, "local"):
            return
        async with self._get_lock():
            connection = self._connections.pop(machine, None)
        if connection is not None:
            await self._close_connection(connection)

    async def reconnect(self, machine):
        """Discard the cached connection and create a fresh one."""
        await self.invalidate(machine)
        return await self.get(machine)

    async def close_all(self):
        """Close every cached transport during launcher shutdown."""
        async with self._get_lock():
            connections = list(self._connections.values())
            self._connections.clear()
        for connection in connections:
            await self._close_connection(connection)

    # Closing is best-effort: cleanup failures must not hide the original
    # launcher error which triggered invalidation.
    @staticmethod
    async def _close_connection(connection):
        close = getattr(connection, "close", None)
        if callable(close):
            close()
        wait_closed = getattr(connection, "wait_closed", None)
        if callable(wait_closed):
            try:
                await wait_closed()
            except Exception:
                logger.debug("error while closing SSH connection", exc_info=True)


# Module-level compatibility path used by the historical function API.
default_connection_manager = ConnectionManager()
