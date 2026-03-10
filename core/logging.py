"""
Structured logging setup. Azure-safe (no emoji), consistent format.

Call setup_logging() once at entry point. All modules use standard
logging.getLogger(__name__).
"""

import logging
import sys


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logger with a clean, Azure-safe format."""
    root = logging.getLogger()
    if root.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(handler)
    root.setLevel(level)
