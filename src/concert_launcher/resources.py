"""Installation of helper scripts on local and remote targets."""

import logging
import os

from . import remote

logger = logging.getLogger(__name__)

RESOURCE_FILES = (
    "concert_launcher_wrapper.bash",
    "concert_launcher_print_ps_tree.py",
)


def resource_path(name):
    return os.path.join(os.path.dirname(__file__), "resources", name)


async def ensure_resources(connection):
    """Ensure helper files exist in ``/tmp`` on the target machine."""
    missing = []
    for name in RESOURCE_FILES:
        code, _, _ = await remote.run_cmd(
            connection,
            "test -f /tmp/{}".format(name),
            throw_on_failure=False,
        )
        if code != 0:
            missing.append(name)

    for name in missing:
        logger.info("installing launcher resource %s", name)
        await remote.putfile(connection, resource_path(name), "/tmp")
