"""AsyncSSH connection caching and recovery."""

import asyncio
import logging

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

    def _get_lock(self):
        loop = asyncio.get_event_loop()
        if self._lock is None or self._lock_loop is not loop:
            self._lock = asyncio.Lock()
            self._lock_loop = loop
        return self._lock

    @staticmethod
    def _parse_machine(machine):
        if not machine or "@" not in machine:
            raise ConfigurationError(
                "remote machine must use the 'user@host' form: {!r}".format(machine)
            )
        user, host = machine.split("@", 1)
        if not user or not host:
            raise ConfigurationError(
                "remote machine must use the 'user@host' form: {!r}".format(machine)
            )
        return user, host

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
            cached = self._connections.get(machine)
            if cached is not None and not self._is_closed(cached):
                return cached
            if cached is not None:
                await self._close_connection(cached)
                self._connections.pop(machine, None)

            user, host = self._parse_machine(machine)
            try:
                logger.info("opening SSH connection to %s", machine)
                connection = await self._connect(
                    host=host,
                    username=user,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                raise RemoteConnectionError(machine, "connect", exc) from exc

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
        async with self._get_lock():
            connections = list(self._connections.values())
            self._connections.clear()
        for connection in connections:
            await self._close_connection(connection)

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


default_connection_manager = ConnectionManager()
