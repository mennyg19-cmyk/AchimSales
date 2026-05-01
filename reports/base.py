"""
Abstract base for report runners.

Provides the common interface that all report runners implement,
plus shared argument parsing for periods and date ranges.
"""

import argparse
import logging
import sys
from abc import ABC, abstractmethod

from config.settings import (
    get_client_id,
    get_client_secret,
    get_company_id,
    get_d365_env_url,
    get_tenant_id,
    validate_d365_config,
)
from core.auth import D365TokenManager
from core.dates import FetchPlan, resolve_fetch_plan
from core.logging import setup_logging

log = logging.getLogger(__name__)


class BaseReportRunner(ABC):
    """Base class for all report runners."""

    report_name: str = "Report"

    def build_arg_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description=self.report_name)
        parser.add_argument("--period", type=str, choices=["daily", "yesterday", "mtd", "last_month", "ytd", "last_7_days", "all_time"],
                            help="Named period (default: all periods)")
        parser.add_argument("--date", type=str, help="Single date YYYY-MM-DD")
        parser.add_argument("--from", dest="from_date", type=str, metavar="DATE", help="Range start YYYY-MM-DD")
        parser.add_argument("--to", dest="to_date", type=str, metavar="DATE", help="Range end YYYY-MM-DD")
        parser.add_argument("--company", type=str, default=None, help="D365 company ID (optional)")
        parser.add_argument("--salesman", type=str, nargs="+", default=None,
                            help="Filter by salesman(s) (e.g. MKolko or MKolko HKaufman or 'all' for all subscribed)")
        parser.add_argument("--customer", type=str, nargs="+", default=None,
                            help="Filter by customer account(s) (e.g. 9300 or 9300 9301 9302)")
        parser.add_argument("--status", type=str, default=None,
                            help="Filter by order status (e.g. 'open' for non-invoiced/non-cancelled)")
        parser.add_argument("--subfolder", type=str, default=None,
                            help="Override output subfolder (e.g. 'Daily'). "
                                 "Used by catch-up logic so --from/--to runs land in the same folder as regular period runs.")
        parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=False,
                            help="Fetch and build reports but skip writing Excel / uploading")
        parser.add_argument("--test", dest="test", action="store_true", default=False,
                            help="Test mode: append _TEST to filenames and override email recipients to TEST_EMAIL")
        return parser

    def resolve_plan(self, args) -> FetchPlan:
        """Build a FetchPlan from parsed CLI args."""
        subfolder = getattr(args, "subfolder", None)
        if args.from_date and args.to_date:
            return resolve_fetch_plan(from_date=args.from_date, to_date=args.to_date,
                                      subfolder_override=subfolder)
        if args.date:
            return resolve_fetch_plan(single_date=args.date)
        if args.period:
            return resolve_fetch_plan(periods=[args.period])
        return resolve_fetch_plan()

    def connect(self, company_id: str | None = None) -> tuple[str, D365TokenManager, str | None]:
        """Validate D365 config and return (base_url, token_manager, company).

        The token manager auto-refreshes before expiry, so long-running
        OData fetches (>30 min) won't fail with 401.
        """
        log.info("Connecting to D365: validating config, acquiring token...")
        validate_d365_config()
        env_url = get_d365_env_url().rstrip("/")
        base_url = (
            f"{env_url}/data/"
            if "/data" not in env_url.lower()
            else (env_url if env_url.endswith("/") else f"{env_url}/")
        )
        token_mgr = D365TokenManager(get_tenant_id(), get_client_id(), get_client_secret(), env_url)
        company = company_id or get_company_id() or None
        log.info("Connected to D365 (company=%s)", company or "(default)")
        return base_url, token_mgr, company

    @property
    def dry_run(self) -> bool:
        """True when ``--dry-run`` was passed on the command line."""
        cli = getattr(self, "_cli_args", None)
        return bool(getattr(cli, "dry_run", False))

    @property
    def test_mode(self) -> bool:
        """True when ``--test`` was passed on the command line."""
        cli = getattr(self, "_cli_args", None)
        return bool(getattr(cli, "test", False))

    @abstractmethod
    def run(self, plan: FetchPlan, company_id: str | None = None) -> None:
        """Execute the report for all periods in the plan."""
        ...

    def main(self, argv: list[str] | None = None) -> int:
        """CLI entry point."""
        setup_logging()
        log.info("%s: parsing arguments...", self.report_name)
        parser = self.build_arg_parser()
        args = parser.parse_args(argv)
        self._cli_args = args

        try:
            plan = self.resolve_plan(args)
            mode_label = " [DRY RUN]" if self.dry_run else (" [TEST]" if self.test_mode else "")
            log.info("%s%s: resolved fetch plan -- %s to %s, %d period(s)",
                     self.report_name, mode_label, plan.fetch_start, plan.fetch_end, len(plan.periods))
            self.run(plan, company_id=getattr(args, "company", None))
            log.info("%s%s: completed successfully", self.report_name, mode_label)
            return 0
        except Exception:
            log.exception("%s: failed", self.report_name)
            return 1
