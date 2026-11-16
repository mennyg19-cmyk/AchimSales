"""Synthetic warehouse sample provider.

Row counts and status totals match the end-of-day Nov 11 2026 gateway snapshot
in the build brief. All identifiers and names are fake — safe for a public repo.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from web.warehouse.filters import counts_by_status, filter_open_rows
from web.warehouse.schema import COLUMNS, STATUS_COLUMNS
from web.warehouse.timeutil import ET, latest_refresh_utc, utc_to_eastern_display

# Snapshot totals from whdashboard-spec-counts (open statuses only).
_STATUS_TOTALS = {
    "shipments": {"Waved": 311, "InProcess": 292, "Open": 34, "Loaded": 5},
    "loads": {"Waved": 318, "InProcess": 286, "Loaded": 4},
    "work": {"Open": 394, "InProcess": 335},
    "clusters": {"Passed": 62, "Open": 47, "InProcess": 2},
}

# Per-area refresh times from the brief (Eastern wall clock on 2026-11-11).
_AREA_AS_OF_ET = {
    "shipments": datetime(2026, 11, 11, 15, 12, 50, tzinfo=ET),
    "loads": datetime(2026, 11, 11, 15, 8, 53, tzinfo=ET),
    "work": datetime(2026, 11, 11, 15, 5, 7, tzinfo=ET),
    "clusters": datetime(2026, 11, 11, 15, 13, 3, tzinfo=ET),
}

_FAKE_CARRIERS = ("SYNTH-CARRIER", "DEMO-FRT", "SAMPLE-XPR")
_FAKE_WH = ("WH-DEMO-1", "WH-DEMO-2")
_FAKE_SITES = ("SITE-A", "SITE-B")


def _blank_row(columns: list[str]) -> dict[str, Any]:
    return {col: None for col in columns}


def _account(i: int) -> str:
    # Synthetic account numbers — not real customers.
    return f"SYN{10000 + (i % 9000)}"


def _order(i: int) -> str:
    return f"SO-DEMO-{100000 + i}"


class SampleWarehouseProvider:
    """In-memory synthetic open lists sized to the Nov 11 2026 status totals."""

    def __init__(self) -> None:
        self._cache: dict[str, list[dict]] = {}

    def get_open_shipments(self) -> list[dict]:
        return list(self._rows("shipments"))

    def get_open_loads(self) -> list[dict]:
        return list(self._rows("loads"))

    def get_open_work(self) -> list[dict]:
        return list(self._rows("work"))

    def get_open_clusters(self) -> list[dict]:
        return list(self._rows("clusters"))

    def data_as_of(self) -> str:
        stamp = max(_AREA_AS_OF_ET.values())
        return stamp.strftime("%Y-%m-%d %H:%M %Z")

    def tile_summary(self) -> dict[str, Any]:
        tiles = []
        for area, totals in _STATUS_TOTALS.items():
            tiles.append({
                "key": area,
                "title": area.replace("_", " ").title() if area != "work" else "Work",
                "total": sum(totals.values()),
                "by_status": dict(totals),
                "coming_soon": False,
                "href": f"/WHdashboard/{area}",
            })
        # Prefer readable titles from schema on the blueprint; keep keys here.
        tiles[0]["title"] = "Shipments"
        tiles[1]["title"] = "Loads"
        tiles[2]["title"] = "Work"
        tiles[3]["title"] = "Clusters"
        tiles.append({
            "key": "waves", "title": "Waves", "total": None,
            "by_status": {}, "coming_soon": True, "href": None,
        })
        tiles.append({
            "key": "due_dates", "title": "Due dates", "total": None,
            "by_status": {}, "coming_soon": True, "href": None,
        })
        return {"data_as_of": self.data_as_of(), "tiles": tiles, "provider": "sample"}

    def _rows(self, area: str) -> list[dict]:
        if area not in self._cache:
            generated = self._generate(area)
            # Include a few closed/shipped/cancelled rows so open filters are
            # exercised; they must not appear in open totals.
            closed = self._closed_extras(area)
            self._cache[area] = filter_open_rows(area, generated + closed)
            # Sanity: open counts must match the brief totals.
            status_col = STATUS_COLUMNS[area]
            got = counts_by_status(self._cache[area], status_col)
            expected = _STATUS_TOTALS[area]
            if got != expected:
                raise RuntimeError(
                    f"Sample {area} status totals {got} != expected {expected}"
                )
        return self._cache[area]

    def _generate(self, area: str) -> list[dict]:
        columns = COLUMNS[area]
        status_col = STATUS_COLUMNS[area]
        as_of_et = _AREA_AS_OF_ET[area]
        as_of_utc = as_of_et.astimezone(timezone.utc)
        rows: list[dict] = []
        n = 0
        for status, count in _STATUS_TOTALS[area].items():
            for _ in range(count):
                n += 1
                row = _blank_row(columns)
                row[status_col] = status
                created_et = as_of_et - timedelta(hours=(n % 48), minutes=(n % 60))
                modified_et = created_et + timedelta(minutes=(n % 90))
                row["createdBy"] = "sample.bot"
                row["modifiedBy"] = "sample.bot"
                row["createdDateTime"] = created_et.strftime("%Y-%m-%d %H:%M:%S")
                row["modifiedDateTime"] = modified_et.strftime("%Y-%m-%d %H:%M:%S")
                if "UpdatedUtc" in row:
                    row["UpdatedUtc"] = as_of_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                if "LastSeenUtc" in row:
                    row["LastSeenUtc"] = as_of_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                if "InsertedUtc" in row:
                    row["InsertedUtc"] = (
                        as_of_utc - timedelta(days=1)
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                if "LastImportedUTC" in row:
                    row["LastImportedUTC"] = as_of_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
                if "IsDeleted" in row:
                    row["IsDeleted"] = 0
                if "dataAreaId" in row:
                    row["dataAreaId"] = "DEMO"
                if "Company" in row:
                    row["Company"] = "DEMO"
                if "InventLocationId" in row:
                    row["InventLocationId"] = _FAKE_WH[n % len(_FAKE_WH)]
                if "InventSiteId" in row:
                    row["InventSiteId"] = _FAKE_SITES[n % len(_FAKE_SITES)]
                if "AccountNum" in row:
                    row["AccountNum"] = _account(n)
                if "OrderNum" in row:
                    row["OrderNum"] = _order(n)
                if "CarrierCode" in row:
                    row["CarrierCode"] = _FAKE_CARRIERS[n % len(_FAKE_CARRIERS)]
                if "RecId" in row:
                    row["RecId"] = 9_000_000 + n
                if "TableId" in row:
                    row["TableId"] = 50000 + (n % 10)

                if area == "shipments":
                    row["ShipmentId"] = f"SHP-DEMO-{n:05d}"
                    row["LoadId"] = f"LD-DEMO-{(n % 400) + 1:04d}"
                    row["WaveId"] = f"WV-DEMO-{(n % 80) + 1:03d}"
                    row["DeliveryName"] = f"Demo Consignee {(n % 50) + 1}"
                    row["Address"] = f"{100 + (n % 200)} Sample Ave"
                    row["WorkTransType"] = "Sales"
                elif area == "loads":
                    row["LoadId"] = f"LD-DEMO-{n:05d}"
                    row["DestinationName"] = f"Demo Destination {(n % 40) + 1}"
                    row["OriginName"] = "Demo Origin DC"
                    row["TrailerNumber"] = f"TRL-{1000 + (n % 200)}"
                    row["ETA"] = (as_of_et + timedelta(days=(n % 5))).strftime(
                        "%Y-%m-%d"
                    )
                elif area == "work":
                    row["WorkId"] = f"WRK-DEMO-{n:05d}"
                    row["ShipmentId"] = f"SHP-DEMO-{(n % 600) + 1:05d}"
                    row["LoadId"] = f"LD-DEMO-{(n % 400) + 1:04d}"
                    row["WaveId"] = f"WV-DEMO-{(n % 80) + 1:03d}"
                    row["WorkTransType"] = "Sales"
                    row["WorkPoolId"] = f"POOL-{(n % 5) + 1}"
                    row["LockedUser"] = "demo.picker" if status == "InProcess" else None
                elif area == "clusters":
                    row["ClusterId"] = f"CL-DEMO-{n:04d}"
                    row["ClusterProfileId"] = f"PROF-{(n % 4) + 1}"
                    row["ClusterType"] = "Pick"
                    row["LockedUser"] = "demo.picker" if status == "InProcess" else None
                    row["SourceFileName"] = "sample_clusters.csv"
                    row["SourceSheetName"] = "clusters"
                    row["SourceRowNumber"] = n
                rows.append(row)
        return rows

    def _closed_extras(self, area: str) -> list[dict]:
        """A few non-open rows so filter unit tests have something to drop."""
        columns = COLUMNS[area]
        status_col = STATUS_COLUMNS[area]
        closed_status = {
            "shipments": "Shipped",
            "loads": "Shipped",
            "work": "Closed",
            "clusters": "Closed",
        }[area]
        extras = []
        for i in range(3):
            row = _blank_row(columns)
            row[status_col] = closed_status
            row["createdBy"] = "sample.bot"
            if area == "shipments":
                row["ShipmentId"] = f"SHP-CLOSED-{i}"
            elif area == "loads":
                row["LoadId"] = f"LD-CLOSED-{i}"
            elif area == "work":
                row["WorkId"] = f"WRK-CLOSED-{i}"
                # Also exercise Cancelled exclusion.
                if i == 0:
                    cancel = dict(row)
                    cancel[status_col] = "Cancelled"
                    cancel["WorkId"] = "WRK-CANCEL-0"
                    extras.append(cancel)
            else:
                row["ClusterId"] = f"CL-CLOSED-{i}"
            extras.append(row)
        return extras


def sample_data_as_of_from_rows(rows: list[dict]) -> str | None:
    """Helper for tests: convert newest UpdatedUtc-style stamp to ET display."""
    latest = latest_refresh_utc(rows)
    if latest is None:
        return None
    return utc_to_eastern_display(latest)
