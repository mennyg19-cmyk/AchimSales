"""Shared mock reference data used by the filter API and the report runner.

Temporary: will be replaced with real SQL Server lookups once the stored
procedures are wired in. Keeping the lists here means the filter dropdowns
and the generated report rows stay consistent (same salesmen, same
customer book splits).
"""

from __future__ import annotations


SALESMEN: list[dict] = [
    {"key": "1", "name": "Alex Morgan"},
    {"key": "2", "name": "Bailey Chen"},
    {"key": "3", "name": "Casey Rivera"},
    {"key": "4", "name": "Drew Patel"},
    {"key": "5", "name": "Elliot Ng"},
    {"key": "6", "name": "Frankie Diaz"},
    {"key": "7", "name": "Gabby Park"},
]


CUSTOMERS: list[dict] = [
    {"key": "C10001", "name": "Atlas Trading Co.",      "salesman": "1"},
    {"key": "C10002", "name": "Bridgepoint Retail",     "salesman": "1"},
    {"key": "C10003", "name": "Cardinal Home Goods",    "salesman": "1"},
    {"key": "C10004", "name": "Delmar Wholesale",       "salesman": "2"},
    {"key": "C10005", "name": "Evergreen Outfitters",   "salesman": "2"},
    {"key": "C10006", "name": "Fairway Distributors",   "salesman": "2"},
    {"key": "C10007", "name": "Glenmore Imports",       "salesman": "3"},
    {"key": "C10008", "name": "Harbor Point Supply",    "salesman": "3"},
    {"key": "C10009", "name": "Ironwood Housewares",    "salesman": "3"},
    {"key": "C10010", "name": "Juniper Mercantile",     "salesman": "4"},
    {"key": "C10011", "name": "Kingsgate Dry Goods",    "salesman": "4"},
    {"key": "C10012", "name": "Larkspur Traders",       "salesman": "4"},
    {"key": "C10013", "name": "Meridian Home",          "salesman": "5"},
    {"key": "C10014", "name": "Northshore Interiors",   "salesman": "5"},
    {"key": "C10015", "name": "Oakridge Supply",        "salesman": "5"},
    {"key": "C10016", "name": "Pinecrest Retail",       "salesman": "6"},
    {"key": "C10017", "name": "Quailridge Imports",     "salesman": "6"},
    {"key": "C10018", "name": "Rosewood Distributors",  "salesman": "6"},
    {"key": "C10019", "name": "Sunnybrook Wholesale",   "salesman": "7"},
    {"key": "C10020", "name": "Tidewater Trading",      "salesman": "7"},
    {"key": "C10021", "name": "Uplands Market",         "salesman": "7"},
    {"key": "C10022", "name": "Valentine Group",        "salesman": "1"},
    {"key": "C10023", "name": "Westlake Supply Co.",    "salesman": "2"},
    {"key": "C10024", "name": "Yorkshire Home",         "salesman": "3"},
    {"key": "C10025", "name": "Zenith Distributors",    "salesman": "4"},
]


def customers_by_salesman(salesman_key: str | None = None) -> list[dict]:
    """Filter customers to a single salesman's book (or return everyone)."""
    if not salesman_key:
        return list(CUSTOMERS)
    return [c for c in CUSTOMERS if c["salesman"] == salesman_key]


def salesman_name(salesman_key: str | None) -> str:
    for s in SALESMEN:
        if s["key"] == salesman_key:
            return s["name"]
    return "Unknown"
