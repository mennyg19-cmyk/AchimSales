"""
Commission percentages by salesman number.

Keys are normalized salesman numbers (no leading zeros).
Values are commission rates as decimals (e.g., 0.05 = 5%).
"""

COMMISSION_PCT: dict[str, float] = {
    "90": 0.03,
    "76": 0.04,
    "71": 0.05,
    "77": 0.05,
    "102": 0.05,
    "80": 0.05,
}

COMMISSION_PCT_2026_PLUS: dict[str, float] = {
    "12": 0.06,
    "29": 0.04,
    "24": 0.06,
}


def get_commission_rate(salesman_number: str, year: int | None = None) -> float:
    """Return commission rate for a salesman number, or 0.0 if not configured."""
    normalized = str(salesman_number).strip().lstrip("0") or "0"
    rate = COMMISSION_PCT.get(normalized, 0.0)
    if year is not None and year >= 2026:
        rate = max(rate, COMMISSION_PCT_2026_PLUS.get(normalized, 0.0))
    return rate


def get_commission_pct_map(year: int | None = None) -> dict[str, float]:
    """Return the full commission map for the given year."""
    result = dict(COMMISSION_PCT)
    if year is not None and year >= 2026:
        result.update(COMMISSION_PCT_2026_PLUS)
    return result
