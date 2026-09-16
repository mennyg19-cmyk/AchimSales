"""
Column detection and numeric conversion utilities.

Single implementations of helpers that were duplicated across 3+ scripts
in the old codebase (norm_col, pick_col, to_number, etc.).
"""

import re

import pandas as pd


def norm_col(name: str) -> str:
    """Normalize a column name: lowercase, strip non-alphanumeric."""
    return re.sub(r"[^a-z0-9]+", "", str(name).strip().lower())


def pick_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find the best matching column in df from a list of candidate names.

    First pass: exact normalized match.
    Second pass: substring match (candidate is contained in column name).
    Returns the original column name or None.
    """
    cols = list(df.columns)
    norm_map = {norm_col(c): c for c in cols}

    for cand in candidates:
        nc = norm_col(cand)
        if nc in norm_map:
            return norm_map[nc]

    for cand in candidates:
        key = norm_col(cand)
        if not key:
            continue
        for n, orig in norm_map.items():
            if key in n:
                return orig

    return None


def to_number(series: pd.Series) -> pd.Series:
    """Convert a string Series to numeric, handling $, commas, and parenthetical negatives."""
    s = series.astype(str).str.strip()
    s = s.str.replace(",", "", regex=False).str.replace("$", "", regex=False)
    s = s.str.replace(r"^\((.*)\)$", r"-\\1", regex=True)
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def rename_columns(df: pd.DataFrame, field_map: dict[str, str]) -> pd.DataFrame:
    """Rename DataFrame columns using a field map. Handles case-insensitive matching.

    field_map: {source_name: target_name}
    Only renames if target doesn't already exist.
    """
    result = df.copy()
    for orig, new in field_map.items():
        if orig in result.columns and new not in result.columns:
            result = result.rename(columns={orig: new})
            continue
        for c in result.columns:
            if c.upper() == orig.upper() and new not in result.columns:
                result = result.rename(columns={c: new})
                break
    return result
