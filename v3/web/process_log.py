"""Process-entry logging. Call before importing the rest of the app."""

from __future__ import annotations

import logging
import os


def configure_process_logging() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
