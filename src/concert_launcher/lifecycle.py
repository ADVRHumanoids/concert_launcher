"""Compatibility imports for process lifecycle operations."""

from .start import execute_process
from .stop import kill

__all__ = ("execute_process", "kill")
