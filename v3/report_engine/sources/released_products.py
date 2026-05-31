"""Adapter: released_products SP rows -> book-price lookup (Number 4).

The released_products SP (rpt.usp_releasedproducts) returns product master
rows. LIVE's "Book Price" is the released product's `SalesPrice`, joined to
invoice lines by ItemNumber (see data/field_maps.py BOOK_PRICE_FIELD_MAP).
We key the map by upper-cased ItemNumber so the Number 4 join is
case-insensitive (matching LIVE's `.str.upper()` join).
"""

from __future__ import annotations

from typing import Iterable, Mapping

from report_engine.lib import first_of, num, text


def to_book_price_map(rows: Iterable[Mapping]) -> dict[str, float | None]:
    """{UPPER(ItemNumber) -> SalesPrice}. A blank/missing price maps to None so
    Book Price renders blank (LIVE shows NaN), not a misleading 0.00."""
    out: dict[str, float | None] = {}
    for raw in rows:
        item = text(first_of(raw, "ItemNumber", "Item", "ItemId", "Item#")).strip().upper()
        if not item or item in out:
            continue
        price_raw = first_of(raw, "SalesPrice", "BookPrice")
        out[item] = num(price_raw) if price_raw is not None else None
    return out
