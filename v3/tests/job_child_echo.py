"""Test-only child that reports success through the temporary job database."""

from __future__ import annotations

import sys
from pathlib import Path

from web.data.connection import Database
from web.data.repositories.jobs import JobRepository


if __name__ == "__main__":
    job_id, precious_path, cache_path = sys.argv[1:]
    JobRepository(Database(Path(precious_path), Path(cache_path))).mark_success(job_id, "child-echo")
