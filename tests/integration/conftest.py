import pytest
import pytest_asyncio

from concert_launcher import Launcher

from .helpers import RemoteHost, SSHProxy, direct_machine, proxy_url


pytestmark = pytest.mark.docker


@pytest_asyncio.fixture
async def remote_a():
    host = await RemoteHost(direct_machine("A")).connect()
    try:
        yield host
    finally:
        await host.close()


@pytest_asyncio.fixture
async def remote_b():
    host = await RemoteHost(direct_machine("B")).connect()
    try:
        yield host
    finally:
        await host.close()


@pytest_asyncio.fixture
async def proxy_a():
    proxy = SSHProxy(proxy_url("A"))
    await proxy.enable()
    try:
        yield proxy
    finally:
        await proxy.enable()


@pytest_asyncio.fixture
async def proxy_b():
    proxy = SSHProxy(proxy_url("B"))
    await proxy.enable()
    try:
        yield proxy
    finally:
        await proxy.enable()


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
