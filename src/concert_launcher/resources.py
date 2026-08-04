"""Install the small helper scripts required on each execution target.

Lifecycle code expects the wrapper and process-tree script under ``/tmp``.
This module keeps deployment idempotent and normalizes permissions after local
copy or SCP.
"""

import logging
import os

from . import remote

logger = logging.getLogger(__name__)

# These files are package resources locally and fixed paths on target machines.
RESOURCE_FILES = (
    "concert_launcher_wrapper.bash",
    "concert_launcher_print_ps_tree.py",
)


def resource_path(name):
    """Return the installed package path for one helper resource."""
    return os.path.join(os.path.dirname(__file__), "resources", name)


async def ensure_resources(connection):
    """Ensure helper files exist in ``/tmp`` on the target machine."""
    # ``putfile`` chooses a local copy or SCP while preserving one deployment
    # path for the lifecycle layer. These files are tiny, and refreshing them
    # on connect keeps already-running labs from using stale helper scripts.
    for name in RESOURCE_FILES:
        logger.info("installing launcher resource %s", name)
        await remote.putfile(connection, resource_path(name), "/tmp")

    # SCP implementations and remote umasks differ. Set deterministic modes so
    # the wrapper is executable even when the copied source mode is not kept.
    await remote.run_cmd(
        connection,
        "chmod 755 /tmp/concert_launcher_wrapper.bash && "
        "chmod 644 /tmp/concert_launcher_print_ps_tree.py",
    )
