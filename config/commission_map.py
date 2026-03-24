"""
Commission percentages by salesman number.

All commission rates are now managed in salesman_map.xlsx (``Commission %`` column).
This module delegates to :func:`config.salesman_excel.get_commission_pct_map`.
"""

import logging

log = logging.getLogger(__name__)


def get_commission_rate(salesman_number: str) -> float:
    """Return commission rate for a salesman number, or 0.0 if not configured."""
    normalized = str(salesman_number).strip().lstrip("0") or "0"
    return get_commission_pct_map().get(normalized, 0.0)


def get_commission_pct_map() -> dict[str, float]:
    """Return the full commission map from salesman_map.xlsx."""
    try:
        from config.salesman_excel import get_commission_pct_map as _xl_map
        return _xl_map()
    except Exception:
        log.warning("Could not load commission map from Excel; returning empty map", exc_info=True)
        return {}
