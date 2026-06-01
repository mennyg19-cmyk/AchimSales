"""Dashboard customer-aggregate repository (cache.db `dashboard_customers`).

Stores precomputed per-customer cadence metrics so the dashboard tiles + table
read fast. Rebuilt wholesale by the mirror refresh (DELETE + bulk insert), the
same full-refresh strategy LIVE uses for dashboard_cache.
"""

from __future__ import annotations

from dataclasses import dataclass

from web.data.connection import Database


@dataclass(frozen=True)
class DashboardCustomer:
    customer_account: str
    customer_name: str
    sales_group: str
    last_order_date: str | None
    order_count: int
    avg_gap_days: float | None
    gap_stdev: float | None
    overdue_threshold: float | None
    days_since_last: int | None
    status: str


class DashboardRepository:
    def __init__(self, db: Database):
        self.db = db

    def replace_all(self, rows: list[DashboardCustomer]) -> int:
        """Full refresh: clear and bulk-insert. Returns the row count written."""
        with self.db.cache() as conn:
            conn.execute("DELETE FROM dashboard_customers")
            conn.executemany(
                "INSERT INTO dashboard_customers(customer_account, customer_name, sales_group,"
                " last_order_date, order_count, avg_gap_days, gap_stdev, overdue_threshold,"
                " days_since_last, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(r.customer_account, r.customer_name, r.sales_group, r.last_order_date,
                  r.order_count, r.avg_gap_days, r.gap_stdev, r.overdue_threshold,
                  r.days_since_last, r.status) for r in rows],
            )
        return len(rows)

    def all(self) -> list[DashboardCustomer]:
        with self.db.cache() as conn:
            rows = conn.execute(
                "SELECT * FROM dashboard_customers ORDER BY customer_name"
            ).fetchall()
        return [self._row(r) for r in rows]

    def get(self, customer_account: str) -> DashboardCustomer | None:
        with self.db.cache() as conn:
            row = conn.execute(
                "SELECT * FROM dashboard_customers WHERE customer_account = ?",
                (customer_account,),
            ).fetchone()
        return self._row(row) if row else None

    def count(self) -> int:
        with self.db.cache() as conn:
            return conn.execute("SELECT COUNT(*) AS n FROM dashboard_customers").fetchone()["n"]

    def last_refreshed(self) -> str | None:
        with self.db.cache() as conn:
            row = conn.execute(
                "SELECT MAX(refreshed_at) AS t FROM dashboard_customers"
            ).fetchone()
        return row["t"] if row else None

    @staticmethod
    def _row(r) -> DashboardCustomer:
        return DashboardCustomer(
            customer_account=r["customer_account"], customer_name=r["customer_name"],
            sales_group=r["sales_group"], last_order_date=r["last_order_date"],
            order_count=r["order_count"], avg_gap_days=r["avg_gap_days"],
            gap_stdev=r["gap_stdev"], overdue_threshold=r["overdue_threshold"],
            days_since_last=r["days_since_last"], status=r["status"],
        )
