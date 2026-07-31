#!/usr/bin/env python3
"""Controllable TCP proxy used to interrupt SSH without stopping its host."""

import asyncio
import json
import os


class ControllableProxy:
    def __init__(self, target_host, target_port):
        self.target_host = target_host
        self.target_port = target_port
        self.enabled = True
        self.connections = set()

    async def handle_ssh(self, client_reader, client_writer):
        if not self.enabled:
            await close_writer(client_writer)
            return

        try:
            server_reader, server_writer = await asyncio.open_connection(
                self.target_host,
                self.target_port,
            )
        except Exception:
            await close_writer(client_writer)
            return

        if not self.enabled:
            await close_writer(client_writer)
            await close_writer(server_writer)
            return

        pair = (client_writer, server_writer)
        self.connections.add(pair)
        try:
            await asyncio.gather(
                relay(client_reader, server_writer),
                relay(server_reader, client_writer),
            )
        finally:
            self.connections.discard(pair)
            await close_writer(client_writer)
            await close_writer(server_writer)

    async def set_enabled(self, enabled):
        self.enabled = enabled
        if enabled:
            return
        connections = list(self.connections)
        self.connections.clear()
        await asyncio.gather(
            *[
                close_writer(writer)
                for pair in connections
                for writer in pair
            ],
            return_exceptions=True,
        )

    async def handle_control(self, reader, writer):
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=2)
            parts = request_line.decode("ascii", errors="replace").split()
            path = parts[1] if len(parts) >= 2 else "/status"
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=2)
                if line in (b"\r\n", b"\n", b""):
                    break

            if path == "/enable":
                await self.set_enabled(True)
                status = 200
            elif path == "/disable":
                await self.set_enabled(False)
                status = 200
            elif path == "/status":
                status = 200
            else:
                status = 404

            body = json.dumps(
                {
                    "enabled": self.enabled,
                    "connections": len(self.connections),
                }
            ).encode("utf-8")
            reason = "OK" if status == 200 else "Not Found"
            writer.write(
                (
                    "HTTP/1.1 {} {}\r\n"
                    "Content-Type: application/json\r\n"
                    "Content-Length: {}\r\n"
                    "Connection: close\r\n"
                    "\r\n"
                ).format(status, reason, len(body)).encode("ascii")
                + body
            )
            await writer.drain()
        finally:
            await close_writer(writer)


async def relay(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                return
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        return
    finally:
        await close_writer(writer)


async def close_writer(writer):
    if writer is None:
        return
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass


async def main():
    target_host = os.environ["TARGET_HOST"]
    target_port = int(os.environ.get("TARGET_PORT", "22"))
    listen_port = int(os.environ.get("LISTEN_PORT", "22"))
    control_port = int(os.environ.get("CONTROL_PORT", "8474"))
    proxy = ControllableProxy(target_host, target_port)

    ssh_server = await asyncio.start_server(
        proxy.handle_ssh,
        "0.0.0.0",
        listen_port,
    )
    control_server = await asyncio.start_server(
        proxy.handle_control,
        "0.0.0.0",
        control_port,
    )
    async with ssh_server, control_server:
        await asyncio.gather(
            ssh_server.serve_forever(),
            control_server.serve_forever(),
        )


if __name__ == "__main__":
    asyncio.run(main())
