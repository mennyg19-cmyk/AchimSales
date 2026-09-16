"""Loads a report's full definition (config + filters + columns + tabs)."""

# === What's in this file ===
# The runner and the web side both need a report's whole definition in one
# object. This reads the four config tables through the repository and packs
# them into a single typed ReportConfig, and refuses a report that isn't active.
#
# ReportConfig -- everything that defines one report
# ConfigLoader.load() -- assemble a report's definition (raises if missing)
# ConfigLoader.load_runnable() -- same, but also refuses a disabled report

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..data.connection import Database
from ..data.repositories.report_configs import STATUS_ACTIVE, ReportConfigRepository


class ReportNotFound(KeyError):
    """No report config exists for this key."""


class ReportNotRunnable(RuntimeError):
    """The report exists but isn't active."""


@dataclass(frozen=True)
class ReportConfig:
    report_key: str
    title: str
    status: str
    sp_name: str
    default_params: dict
    filters: list[dict]
    columns: list[dict]
    tabs: list[dict]


class ConfigLoader:
    def __init__(self, db: Database) -> None:
        self._repo = ReportConfigRepository(db)

    def load(self, report_key: str) -> ReportConfig:
        row = self._repo.get_config(report_key)
        if row is None:
            raise ReportNotFound(report_key)
        return ReportConfig(
            report_key=row["report_key"],
            title=row["title"],
            status=row["status"],
            sp_name=row["sp_name"] or "",
            default_params=row.get("default_params") or {},
            filters=self._repo.get_filters(report_key),
            columns=self._repo.get_columns(report_key),
            tabs=self._repo.get_tabs(report_key),
        )

    def load_runnable(self, report_key: str) -> ReportConfig:
        config = self.load(report_key)
        if config.status != STATUS_ACTIVE:
            raise ReportNotRunnable(report_key)
        return config

    def list_active(self) -> list[dict[str, Any]]:
        return self._repo.list_active()
