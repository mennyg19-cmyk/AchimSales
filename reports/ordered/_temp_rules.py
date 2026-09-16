"""
TEMPORARY business rules for the Ordered Report.

This file exists solely for short-lived overrides that should be removed
once the underlying D365 processes are corrected.  Each rule is a function
that mutates the merged DataFrame in place and returns it.

To remove a rule: delete the function body (or the whole file) and remove
the one-line call in builder.py.
"""

import logging

import pandas as pd

log = logging.getLogger(__name__)


def apply_temp_rules(merged: pd.DataFrame) -> pd.DataFrame:
    """Apply all temporary rules and return the (possibly mutated) DataFrame."""
    merged = _amazon_open_to_cancelled(merged)
    return merged


# ── Rule 1: Amazon (9300 / 9301) open qty → cancelled ─────────────────
# Amazon open lines that are not released are always cancelled by the next
# business day.  Until the D365 cancellation job runs before the report,
# we force them here so reports are accurate.
#
# For fully open lines: entire qty becomes cancelled.
# For partially shipped lines: the open portion becomes cancelled,
#   QtyCancelled = QtyOrdered - QtyShipped,  QtyRemainder = QtyShipped.
#
# DELETE THIS FUNCTION (and the call above) once the D365 job is fixed.

_AMAZON_ACCOUNTS = {"9300", "9301"}


def _amazon_open_to_cancelled(merged: pd.DataFrame) -> pd.DataFrame:
    if merged.empty:
        return merged

    acct_col = None
    for candidate in ("CustomerAccount", "CustomerAccountNumber"):
        if candidate in merged.columns:
            acct_col = candidate
            break
    if acct_col is None:
        return merged

    is_amazon = merged[acct_col].astype(str).str.strip().isin(_AMAZON_ACCOUNTS)
    has_open_qty = merged["QtyOpen"] > 1e-9
    mask = is_amazon & has_open_qty

    n = mask.sum()
    if n == 0:
        return merged

    shipped = merged.loc[mask, "QtyShipped"].fillna(0)
    ordered = merged.loc[mask, "QtyOrdered"].fillna(0)

    merged.loc[mask, "QtyCancelled"] = ordered - shipped
    merged.loc[mask, "QtyOpen"] = 0.0
    merged.loc[mask, "QtyReleased"] = 0.0
    merged.loc[mask, "QtyRemainder"] = shipped

    fully_open = mask & (shipped < 1e-9)
    merged.loc[fully_open, "DisplayLineStatus"] = "Cancelled"

    partially_shipped = mask & (shipped >= 1e-9)
    merged.loc[partially_shipped, "DisplayLineStatus"] = "Cancelled"

    log.info("TEMP RULE: reclassified %d Amazon line(s) open qty as Cancelled "
             "(fully open: %d, partial: %d)",
             n, fully_open.sum(), partially_shipped.sum())
    return merged
