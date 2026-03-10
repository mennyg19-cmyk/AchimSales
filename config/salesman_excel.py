"""
Read salesman mappings from the editable Excel file (salesman_map.xlsx).

The Excel file has columns:
  Key, Number, FullName, DisplayName, Email,
  Recv_Ordered, Recv_Invoiced, Recv_Salesman, Recv_Number4, Recv_CustomerActivity,
  Recv_MasterSalesman, Recv_MasterCustomerActivity

This module is the primary data source for salesman lookups.
salesman_map.py delegates here and falls back to its hardcoded dict
if the Excel file is missing.
"""

import logging
import os
import re
from functools import lru_cache
from typing import NamedTuple

from openpyxl import load_workbook

log = logging.getLogger(__name__)

_XLSX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "salesman_map.xlsx")

REPORT_KEYS = ("ordered", "invoiced", "salesman", "number_4", "customer_activity",
                "master_salesman", "master_customer_activity")

_SUBSCRIPTION_COLUMNS = {
    "Recv_Ordered": "ordered",
    "Recv_Invoiced": "invoiced",
    "Recv_Salesman": "salesman",
    "Recv_Number4": "number_4",
    "Recv_CustomerActivity": "customer_activity",
    "Recv_MasterSalesman": "master_salesman",
    "Recv_MasterCustomerActivity": "master_customer_activity",
}


class SalesmanRecord(NamedTuple):
    number: str
    full_name: str
    display_name: str
    email: str
    subscriptions: dict[str, bool]


DEFAULT_SALESMAN = SalesmanRecord(
    number="?unassigned",
    full_name="Unassigned",
    display_name="Unassigned",
    email="",
    subscriptions={k: False for k in REPORT_KEYS},
)


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s).strip().lower()) if s else ""


def _to_bool(val) -> bool:
    if val is None:
        return False
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    return s in ("true", "1", "yes", "y")


@lru_cache(maxsize=1)
def load_salesman_map(path: str | None = None) -> dict[str, SalesmanRecord]:
    """Load the salesman map from the Excel file.

    Returns {normalized_key: SalesmanRecord}.
    """
    xlsx = path or _XLSX_PATH
    if not os.path.isfile(xlsx):
        log.warning("Salesman map Excel not found: %s", xlsx)
        return {}

    wb = load_workbook(xlsx, read_only=True, data_only=True)
    ws = wb.active

    header_map: dict[str, int] = {}
    result: dict[str, SalesmanRecord] = {}
    first_row = True

    for row in ws.iter_rows(values_only=False):
        if first_row:
            for cell in row:
                if cell.value:
                    header_map[str(cell.value).strip()] = cell.column - 1
            first_row = False
            continue

        vals = [cell.value for cell in row]
        if not vals or not vals[0]:
            continue

        key = _norm_key(str(vals[0]))
        number = str(vals[1] or "").strip() if len(vals) > 1 else ""
        full_name = str(vals[2] or "").strip() if len(vals) > 2 else ""
        display_name = str(vals[3] or "").strip() if len(vals) > 3 else ""
        email = str(vals[4] or "").strip() if len(vals) > 4 else ""

        subs: dict[str, bool] = {}
        for col_name, report_key in _SUBSCRIPTION_COLUMNS.items():
            col_idx = header_map.get(col_name)
            if col_idx is not None and col_idx < len(vals):
                subs[report_key] = _to_bool(vals[col_idx])
            else:
                subs[report_key] = bool(email)

        result[key] = SalesmanRecord(
            number=number,
            full_name=full_name,
            display_name=display_name,
            email=email,
            subscriptions=subs,
        )

    wb.close()
    log.info("Loaded %d salesmen from %s", len(result), xlsx)
    return result


def lookup_salesman_xl(sales_group: str) -> SalesmanRecord:
    """Look up salesman by raw sales group string."""
    key = _norm_key(sales_group)
    return load_salesman_map().get(key, DEFAULT_SALESMAN)


def get_salesman_email(sales_group: str) -> str:
    return lookup_salesman_xl(sales_group).email


def get_salesman_display_name_xl(sales_group: str) -> str:
    return lookup_salesman_xl(sales_group).display_name


def get_salesman_full_name_xl(sales_group: str) -> str:
    return lookup_salesman_xl(sales_group).full_name


def get_salesman_number_xl(sales_group: str) -> str:
    return lookup_salesman_xl(sales_group).number


def wants_report(sales_group: str, report_key: str) -> bool:
    """Check if a salesman wants to receive a specific report.

    report_key must be one of: ordered, invoiced, salesman, number_4, customer_activity,
    master_salesman, master_customer_activity
    """
    rec = lookup_salesman_xl(sales_group)
    if not rec.email:
        return False
    return rec.subscriptions.get(report_key, False)


def pad_salesman_number(num: str) -> str:
    """Zero-pad numeric salesman numbers to 3 digits."""
    s = str(num).strip()
    if re.fullmatch(r"\d+", s):
        return s.zfill(3)
    return s


def get_all_active_salesmen() -> dict[str, SalesmanRecord]:
    """Return only salesmen with non-empty email addresses."""
    return {k: v for k, v in load_salesman_map().items() if v.email}


def get_all_salesmen_keys() -> list[str]:
    """Return all salesman keys (including inactive/no-email)."""
    return list(load_salesman_map().keys())


def get_report_subscribers(report_key: str) -> list[tuple[str, str]]:
    """Return [(display_name, email)] for everyone subscribed to a report.

    Useful for master report distribution where the recipient is not
    necessarily a salesman in the data -- just someone who wants the file.
    """
    result = []
    for key, rec in load_salesman_map().items():
        if rec.email and rec.subscriptions.get(report_key, False):
            result.append((rec.display_name or key, rec.email))
    return result
