"""Rules that decide whether a conditional tab should appear at all."""

# === What's in this file ===
# Some tabs only make sense for certain data: "Totals by Salesman" only when
# there's more than one salesman, "Audit - Reversals" only when an invoice has
# both a positive and a negative total. A tab's config names one of these rules;
# the engine asks here whether to build the tab.
#
# has_multiple_salesmen() -- 2+ distinct salesmen present
# has_reversals() -- some invoice number carries both a + and a - total
# evaluate() -- look up a named condition and run it (unknown name -> show tab)

from __future__ import annotations

from typing import Callable, Sequence

from .lib import num

Condition = Callable[[Sequence[dict]], bool]


def has_multiple_salesmen(rows: Sequence[dict]) -> bool:
    distinct = {(r.get("Salesman") or "").strip() for r in rows if (r.get("Salesman") or "").strip()}
    return len(distinct) >= 2


def reversal_invoice_numbers(rows: Sequence[dict]) -> set[str]:
    extents: dict[str, list[float]] = {}
    for r in rows:
        key = r.get("InvoiceNumber") or ""
        if not key:
            continue
        total = num(r.get("Total Invoice"))
        lohi = extents.setdefault(key, [float("inf"), float("-inf")])
        lohi[0] = min(lohi[0], total)
        lohi[1] = max(lohi[1], total)
    return {k for k, (lo, hi) in extents.items() if lo < 0 < hi}


def has_reversals(rows: Sequence[dict]) -> bool:
    return bool(reversal_invoice_numbers(rows))


_CONDITIONS: dict[str, Condition] = {
    "has_multiple_salesmen": has_multiple_salesmen,
    "has_reversals": has_reversals,
}


def evaluate(name: str, rows: Sequence[dict]) -> bool:
    condition = _CONDITIONS.get(name)
    if condition is None:
        return True
    return condition(rows)
