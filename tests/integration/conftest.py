import pytest
import pytest_asyncio

from concert_launcher import Launcher

from .helpers import RemoteHost, machine


pytestmark = pytest.mark.docker


@pytest_asyncio.fixture
async def remote_a():
    host = await RemoteHost(machine("A")).connect()
    try:
        yield host
    finally:
        await host.close()


@pytest_asyncio.fixture
async def remote_b():
    host = await RemoteHost(machine("B")).connect()
    try:
        yield host
    finally:
        await host.close()


@pytest_asyncio.fixture
async def launcher_factory():
    launchers = []

    def create(config):
        launcher = Launcher(config)
        launchers.append(launcher)
        return launcher

    try:
        yield create
    finally:
        for launcher in launchers:
            await launcher.close()
