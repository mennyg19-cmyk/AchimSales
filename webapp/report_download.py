"""Safe download of report workbooks the current user already produced."""

from __future__ import annotations

import os


def is_under_root(path: str, root: str) -> bool:
    real = os.path.realpath(path)
    root_real = os.path.realpath(root)
    try:
        return os.path.commonpath([real, root_real]) == root_real
    except ValueError:
        return False


def resolve_history_xlsx(filepath: str, reports_root: str, owned_paths) -> str | None:
    """Return the real path if it is an owned .xlsx under reports_root, else None."""
    if not filepath or not filepath.endswith(".xlsx"):
        return None
    real = os.path.realpath(filepath)
    if not is_under_root(real, reports_root):
        return None
    owned = {os.path.realpath(p) for p in owned_paths if p}
    if real not in owned:
        return None
    if not os.path.isfile(real):
        return None
    return real
