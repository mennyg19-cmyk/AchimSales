"""CLI entry: python -m tools.parity"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from tools.parity.clients import LiveClient, ParityError, TestClient
from tools.parity.report import compare_pair, write_index, write_report
from tools.parity.scenarios import DEFAULT_PARAMS, REPORTS

log = logging.getLogger("parity")
EASTERN = ZoneInfo("America/New_York")


def _out_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    stamp = datetime.now(EASTERN).strftime("%Y%m%d-%H%M%S")
    return Path(".scratch") / "parity" / stamp


def _parse_params(raw: list[str]) -> dict:
    """Parse --param KEY=VALUE flags into a dict (values stay strings)."""
    out: dict = {}
    for item in raw:
        if "=" not in item:
            raise SystemExit(f"--param expects KEY=VALUE, got {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"--param expects KEY=VALUE, got {item!r}")
        out[key] = value.strip()
    return out


def _build_clients(args: argparse.Namespace) -> tuple[LiveClient, TestClient]:
    # Single request timeout matches --timeout so big Excel downloads / slow
    # run POSTs don't die on the HttpClient default of 60s.
    http_timeout = max(float(args.timeout), 60.0)
    live = LiveClient(args.base_url, timeout=http_timeout)
    test = TestClient(args.base_url, mount=args.test_mount, timeout=http_timeout)

    auth = (args.auth or os.environ.get("PARITY_AUTH") or "cookie").lower()
    if auth == "dev":
        live.login_dev()
        test.login_dev(
            email=os.environ.get("PARITY_DEV_EMAIL", "parity-admin@localhost"),
            role=os.environ.get("PARITY_DEV_ROLE", "developer"),
        )
        return live, test

    live_cookie = args.live_cookie or os.environ.get("PARITY_LIVE_COOKIE", "")
    test_cookie = args.test_cookie or os.environ.get("PARITY_TEST_COOKIE", "")
    if not live_cookie or not test_cookie:
        raise SystemExit(
            "Cookie auth needs PARITY_LIVE_COOKIE (session) and "
            "PARITY_TEST_COOKIE (v3_session).\n"
            "Sign in once in the browser, copy each cookie value, then re-run.\n"
            "Or use --auth dev against a local server with DEV_BYPASS_AUTH / auth_mode=dev."
        )
    live.login_cookie(live_cookie)
    test.login_cookie(test_cookie)
    return live, test


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare live (/) vs /test report Excel output")
    parser.add_argument("--base-url", default=os.environ.get("PARITY_BASE_URL", "https://reports.achimonline.com"))
    parser.add_argument("--test-mount", default=os.environ.get("PARITY_TEST_MOUNT", "/test"))
    parser.add_argument("--auth", choices=("cookie", "dev"), default=None)
    parser.add_argument("--live-cookie", default=None)
    parser.add_argument("--test-cookie", default=None)
    parser.add_argument("--report", action="append", dest="reports",
                        help="Report key (repeatable). Default: all five parity reports.")
    parser.add_argument(
        "--param", action="append", default=[], metavar="KEY=VALUE",
        help="Override default params for every selected report (repeatable). "
             "Example: --param period=last_month",
    )
    parser.add_argument("--out", default=None, help="Output directory (default .scratch/parity/<stamp>)")
    parser.add_argument("--tolerance", type=float, default=0.01)
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("PARITY_TIMEOUT", "1800")))
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    param_overrides = _parse_params(args.param)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    reports = tuple(args.reports) if args.reports else REPORTS
    unknown = [r for r in reports if r not in DEFAULT_PARAMS]
    if unknown:
        raise SystemExit(f"Unknown report(s): {unknown}. Known: {list(DEFAULT_PARAMS)}")

    out_dir = _out_dir(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("Output: %s", out_dir.resolve())
    log.info("Base URL: %s", args.base_url)

    try:
        live, test = _build_clients(args)
    except ParityError as exc:
        log.error("%s", exc)
        return 2

    index_rows: list[dict] = []
    any_fail = False

    for key in reports:
        params = dict(DEFAULT_PARAMS[key])
        params.update(param_overrides)
        live_xlsx = out_dir / f"{key}__live.xlsx"
        test_xlsx = out_dir / f"{key}__test.xlsx"
        detail = f"{key}.md"
        detail_path = out_dir / detail
        err: str | None = None
        comparison = None
        try:
            log.info("=== %s (params=%s) ===", key, params)
            live.run_and_download(key, params, live_xlsx, timeout_seconds=args.timeout)
            test.run_and_download(key, params, test_xlsx, timeout_seconds=args.timeout)
            comparison = compare_pair(live_xlsx, test_xlsx, tolerance=args.tolerance)
            write_report(
                detail_path,
                report_key=key,
                params=params,
                live_path=live_xlsx,
                test_path=test_xlsx,
                comparison=comparison,
            )
            status = "MATCH" if comparison.is_match else "DIFF"
            if not comparison.is_match:
                any_fail = True
            index_rows.append({
                "report": key,
                "status": status,
                "diffs": comparison.total_diffs,
                "detail": detail,
            })
            log.info("%s -> %s (%s diffs)", key, status, comparison.total_diffs)
        except Exception as exc:  # noqa: BLE001 - surface every report failure in the index
            any_fail = True
            err = str(exc)
            log.exception("%s failed", key)
            write_report(
                detail_path,
                report_key=key,
                params=params,
                live_path=live_xlsx if live_xlsx.exists() else None,
                test_path=test_xlsx if test_xlsx.exists() else None,
                comparison=None,
                error=err,
            )
            index_rows.append({
                "report": key,
                "status": "ERROR",
                "diffs": "—",
                "detail": detail,
            })

    index = write_index(out_dir, index_rows)
    log.info("Index: %s", index.resolve())
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
