import asyncio
import sys
from pathlib import Path

import pytest


pytestmark = [pytest.mark.docker, pytest.mark.asyncio]
EXAMPLES = Path("/workspace/examples/docker")


async def run_example(*command):
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=str(EXAMPLES),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await process.communicate()
    output = stdout.decode("utf-8", errors="replace")
    assert process.returncode == 0, output
    return output


async def test_documented_cli_example_runs_end_to_end():
    output = await run_example("bash", "./cli_demo.sh")
    assert "Start a cross-host dependency graph" in output
    assert "dependency-ready" in output
    assert "RUNNING" in output


async def test_documented_asyncio_api_example_runs_end_to_end():
    output = await run_example(sys.executable, "./api_demo.py")
    assert "api-probe-ready" in output
    assert "state heartbeat_a: RUNNING" in output
    assert "collected lines:" in output
    assert "\033" not in output


async def test_documented_recovery_example_runs_end_to_end():
    output = await run_example(sys.executable, "./recovery_demo.py")
    assert "before outage: RUNNING" in output
    assert "caught typed failure for: tester@ssh-proxy-a" in output
    assert "after recovery: RUNNING" in output
