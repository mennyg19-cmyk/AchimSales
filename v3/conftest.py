"""Pytest bootstrap: put the v3 root on sys.path so `web` and `report_engine`
import as top-level packages no matter where pytest is invoked from.
"""

import sys
from pathlib import Path

_V3_ROOT = Path(__file__).resolve().parent
if str(_V3_ROOT) not in sys.path:
    sys.path.insert(0, str(_V3_ROOT))
