#!/usr/bin/env python3
"""Copy People, views, and schedules from the old site's precious.db.

Save precious.db from the live Azure box, then:

  python import-precious.py path/to/precious.db
  python import-precious.py path/to/precious.db --dest app/data/home.sqlite

On Windows:  .\\import-precious.ps1 -Precious path\\to\\precious.db

Existing emails stay. Dummy views/schedules are wiped, then live column tables
are copied (not the old JSON blob backups).
"""

from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).resolve().parent / "app"
sys.path.insert(0, str(APP))

from import_precious import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
