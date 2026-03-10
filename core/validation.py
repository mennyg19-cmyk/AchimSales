"""
Output validation for report DataFrames.

Call ``validate_output()`` after ``build_report()`` returns a DataFrame
to verify that all expected columns are present before writing Excel.
"""

import logging

import pandas as pd

log = logging.getLogger(__name__)


def validate_output(
    df: pd.DataFrame,
    expected_columns: list[str],
    report_name: str,
) -> None:
    """Raise ``ValueError`` if required columns are missing from *df*.

    Also logs a summary of the validation for auditability.
    """
    if df.empty:
        log.info("%s validation: DataFrame is empty, skipping column check", report_name)
        return

    missing = [c for c in expected_columns if c not in df.columns]
    if missing:
        raise ValueError(f"{report_name}: missing expected columns: {missing}")

    log.debug(
        "%s validation passed: %d rows, %d/%d expected columns present",
        report_name, len(df), len(expected_columns), len(df.columns),
    )
