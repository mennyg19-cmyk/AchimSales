"""
Salesman mappings -- thin wrapper over salesman_excel.py.

All lookup functions try the Excel-based loader first. If the Excel file
is missing or unreadable, they fall back to the hardcoded SALESMAN_MAP
dict below. This ensures existing reports keep working even if the
.xlsx is deleted.

The hardcoded dict is intentionally kept as a safety net and should
mirror the Excel file's contents. To update salesman data, edit
salesman_map.xlsx -- not this file.
"""

import logging
import re

log = logging.getLogger(__name__)

# ── Hardcoded fallback (safety net) ──────────────────────────────────

SALESMAN_MAP: dict[str, tuple[str, str, str]] = {
    "mkolko":                      ("012",        "Mendy Kolko",                     "MKolko"),
    "hkaufman":                    ("029",        "Herschel Kaufman",                "HKaufman"),
    "house":                       ("099",        "ACHIM HOUSE ACCOUNT",             "House"),
    "blevin":                      ("024",        "Bruce Levin",                     "BLevin"),
    "mgrego":                      ("102",        "Meir Grego",                      "MGrego"),
    "agrossman":                   ("042",        "Avi Grossman",                    "AGrossman"),
    "jweigand":                    ("076",        "Janice Weigand",                  "JWeigand"),
    "lcwalker":                    ("077",        "Lisa Carter-Walker",              "LCWalker"),
    "unassigned":                  ("?unassigned","Unassigned",                      "Unassigned"),
    "pmazer":                      ("071",        "Pete Mazer",                      "PMazer"),
    "integrated":                  ("090",        "Integrted Sales Solutns II,LLC",  "Integrated"),
    "redwards":                    ("080",        "Reggie Edwards",                  "REdwards"),
    "howiesiegal":                 ("001",        "Howie Siegal",                    "Howie Siegal"),
    "xgeorgedaniels":              ("026",        "X-George Daniels",                "X-George Daniels"),
    "xedweiner":                   ("032",        "X-Ed Weiner",                     "X-Ed Weiner"),
    "xmoshestein":                 ("064",        "X-Moshe Stein",                   "X-Moshe Stein"),
    "dcmarketingllc":              ("073",        "DC Marketing, LLC",               "DC Marketing"),
    "jodifarello":                 ("101",        "Jodi Farello",                    "Jodi Farello"),
    "joshbenjamin":                ("089",        "Josh Benjamin",                   "Josh Benjamin"),
    "marcwatt":                    ("084",        "Marc Watt",                       "Marc Watt"),
    "jimhinchion":                 ("082",        "Jim Hinchion",                    "Jim Hinchion"),
    "nasdekhomefashionscorp":      ("048",        "Nasdek Home Fashions Corp.",      "Nasdek"),
}

DEFAULT_SALESMAN = ("?unassigned", "Unassigned", "Unassigned")


def _norm_key(s: str) -> str:
    """Normalize a sales group string for lookup."""
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower()) if s else ""


def _fallback_lookup(sales_group: str) -> tuple[str, str, str]:
    key = _norm_key(sales_group)
    return SALESMAN_MAP.get(key, DEFAULT_SALESMAN)


# ── Public API (Excel-first, fallback to dict) ──────────────────────

def lookup_salesman(sales_group: str) -> tuple[str, str, str]:
    """Look up salesman by raw sales group string.

    Returns (number, full_name, display_name).
    """
    try:
        from config.salesman_excel import lookup_salesman_xl
        rec = lookup_salesman_xl(sales_group)
        return (rec[0], rec[1], rec[2])
    except Exception:
        log.debug("Excel lookup failed for '%s', using fallback dict", sales_group, exc_info=True)
        return _fallback_lookup(sales_group)


def get_salesman_number(sales_group: str) -> str:
    try:
        from config.salesman_excel import get_salesman_number_xl
        rec_num = get_salesman_number_xl(sales_group)
        if rec_num and rec_num != "?unassigned":
            return rec_num
    except Exception:
        log.debug("Excel salesman number lookup failed for '%s'", sales_group, exc_info=True)
    return _fallback_lookup(sales_group)[0]


def get_salesman_full_name(sales_group: str) -> str:
    try:
        from config.salesman_excel import get_salesman_full_name_xl
        return get_salesman_full_name_xl(sales_group)
    except Exception:
        log.debug("Excel salesman full name lookup failed for '%s'", sales_group, exc_info=True)
        return _fallback_lookup(sales_group)[1]


def get_salesman_display_name(sales_group: str) -> str:
    try:
        from config.salesman_excel import get_salesman_display_name_xl
        return get_salesman_display_name_xl(sales_group)
    except Exception:
        log.debug("Excel salesman display name lookup failed for '%s'", sales_group, exc_info=True)
        return _fallback_lookup(sales_group)[2]


def pad_salesman_number(num: str) -> str:
    """Zero-pad numeric salesman numbers to 3 digits."""
    try:
        from config.salesman_excel import pad_salesman_number as _pad
        return _pad(num)
    except Exception:
        log.debug("Excel pad_salesman_number failed for '%s'", num, exc_info=True)
        s = str(num).strip()
        if re.fullmatch(r"\d+", s):
            return s.zfill(3)
        return s
