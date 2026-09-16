"""Adapter: customer_master SP rows -> CustomerFact (customer universe).

Used by the Customer Activity report. The web layer pulls the universe live
from the customer_master SP each run and falls back to the local mirror when
the API is down (owner decision); either feed produces the same row shape, so
this adapter accepts the common field-name variants.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from report_engine.facts import CustomerFact
from report_engine.lib import first_of, iso_date, map_release, sales_group_of, text


def to_fact(raw: Mapping) -> CustomerFact:
    customer_account = text(first_of(
        raw, "CustomerAccount", "customer_account", "customeraccount", "AccountNum"))
    return CustomerFact(
        source="reporting_api",
        customer_account=customer_account,
        customer_name=text(first_of(raw, "CustomerName", "customer_name", "customername", "Name")),
        sales_group=sales_group_of(
            raw, "SalesGroup", "sales_group", "salesgroup", "Salesman",
            customer_account=customer_account),
        last_order_date=iso_date(first_of(raw, "LastOrderDate", "last_order_date")),
    )


def to_facts(rows: Iterable[Mapping]) -> list[CustomerFact]:
    return map_release(rows, to_fact)
