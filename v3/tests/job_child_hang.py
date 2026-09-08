"""Test-only child that waits forever, optionally ignoring SIGTERM."""

from __future__ import annotations

import signal
import sys
import time


if __name__ == "__main__":
    if sys.argv[1:] == ["ignore-sigterm"]:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True:
        time.sleep(1)
