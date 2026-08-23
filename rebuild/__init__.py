"""The rebuilt sales reports app (presentation layer over SQL-computed reports).

Mounted by the repository-root wsgi.py onto a temporary slot until cutover.
"""

from .app import bootstrap_background, create_app, get_config
from .config import load_config

__all__ = ["create_app", "bootstrap_background", "get_config", "load_config"]
