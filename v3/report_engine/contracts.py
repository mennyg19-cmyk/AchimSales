"""Report semantic contracts + drift-decision ledger.

Rule 1/2: no calculation rule is chosen silently. Every audited "drift" point is
recorded here as a DriftDecision. Until a human signs off, `signed_off=False` and
the builder uses `chosen=LIVE_ROOT` behaviour, flagged PROVISIONAL. The parity
harness asserts the chosen behaviour matches root for every signed-off case.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DriftChoice(str, Enum):
    LIVE_ROOT = "live_root"   # replicate the trusted production (root) behaviour
    TEST_V2 = "test_v2"       # the sandbox's divergent behaviour
    NEW = "new"               # a deliberately new rule (requires written rationale)


@dataclass(frozen=True)
class DriftDecision:
    """One business-meaningful calculation choice that needs human sign-off."""
    report: str
    key: str
    question: str
    chosen: DriftChoice = DriftChoice.LIVE_ROOT
    signed_off: bool = False
    owner: str = ""
    rationale: str = ""

    @property
    def provisional(self) -> bool:
        return not self.signed_off


@dataclass(frozen=True)
class ReportContract:
    """One-page semantic contract for a report (pre-build gate, plan section 7)."""
    key: str
    title: str
    filters: tuple[str, ...] = ()
    source_facts: tuple[str, ...] = ()
    role_scoping: str = ""
    tabs: tuple[str, ...] = ()
    drift: tuple[DriftDecision, ...] = field(default_factory=tuple)

    def unsigned_drift(self) -> tuple[DriftDecision, ...]:
        return tuple(d for d in self.drift if d.provisional)


# --- Drift ledger -----------------------------------------------------------
# Sourced from test/docs/v2-audit-and-rebuild-opus48.md section 8. All start
# PROVISIONAL (signed_off=False) and default to LIVE_ROOT. The web layer surfaces
# any unsigned drift into v3/REVIEW-LOG.md for the human.

DRIFT_LEDGER: tuple[DriftDecision, ...] = (
    DriftDecision("invoiced", "tariff_source",
                  "Tariff from sales-LINE (SL_TariffCharges) vs sales-HEADER (SH_TariffCharges)?"),
    DriftDecision("invoiced", "credit_detection",
                  "Detect credits by substring 'contains' vs invoice-number prefix?"),
    DriftDecision("ordered", "summary_remainder",
                  "Definition of the Summary tab remainder (ordered - released - shipped?).",
                  chosen=DriftChoice.NEW, signed_off=True, owner="menny",
                  rationale="User chose: Ordered - Released - Shipped - Cancelled (differs from live which omits cancelled)."),
    DriftDecision("ordered", "status_qty_engine",
                  "Status/qty derivation: WHS + packing-slip joins (root) vs flat SP rows (web)."),
    DriftDecision("ordered", "amazon_temp_rule",
                  "Amazon 9300/9301 temporary-item special handling."),
    DriftDecision("ordered", "error_item_filter",
                  "Exclusion of rows flagged 'ERROR ITEM'."),
    DriftDecision("number_4", "book_price",
                  "Book Price column source/derivation."),
    DriftDecision("number_4", "free_text_exclusion",
                  "Exclusion of free-text (non-item) invoice lines."),
    DriftDecision("salesman", "group_key_cardinality",
                  "Salesman grouping grain (one row per SalesGroup vs combined)."),
    DriftDecision("customer_activity", "last_order_grain",
                  "Last-order grain: sales header vs sales line."),
)


def unsigned_drift() -> tuple[DriftDecision, ...]:
    return tuple(d for d in DRIFT_LEDGER if d.provisional)
