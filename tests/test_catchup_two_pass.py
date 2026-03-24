"""
Simulate the two-pass catch-up logic for nightly all-periods runs.

Scenario: Today is 2026-03-25 (Tuesday). The nightly ordered run (no args)
last succeeded on 2026-03-23 (Sunday). Monday's nightly run was missed.
The catch-up should:
  Pass 1: --from 2026-03-23 --to 2026-03-24 --subfolder Daily  (missed days)
  Pass 2: (no args) -> daily + mtd + ytd + last_7_days          (all periods)

Usage:
    python tests/test_catchup_two_pass.py
"""

import csv
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "runbooks"))

EASTERN = ZoneInfo("America/New_York")
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"

LOG_COLS = ["timestamp", "report_name", "status", "duration_sec",
            "rows_output", "files_uploaded", "args", "error"]


def _make_run_log(rows: list[dict]) -> str:
    """Write a temporary run_log.csv and return its path."""
    path = os.path.join(tempfile.gettempdir(), "test_catchup_run_log.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_COLS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)
    return path


def test_nightly_two_pass():
    """Nightly ordered (no args): missed 1 day -> two-pass catch-up."""
    import universal_runbook as rb

    sim_now = datetime(2026, 3, 25, 23, 7, tzinfo=EASTERN)
    rb._SIMULATED_NOW = sim_now

    log_path = _make_run_log([
        {"timestamp": "2026-03-23 23:27:05", "report_name": "Ordered Report",
         "status": "SUCCESS", "args": ""},
    ])

    merged_args = ""
    argv = []
    result = rb._maybe_inject_catchup_args(argv, merged_args, log_path, "Ordered Report")

    ok = (isinstance(result, tuple)
          and len(result) == 3
          and result[0] == rb._CATCHUP_THEN_NORMAL)

    print(f"\n--- Test: Nightly all-periods with 2-day gap ---")
    print(f"  Simulated now:  {sim_now.date()}")
    print(f"  Last success:   2026-03-23")
    print(f"  Gap:            2 days")
    print(f"  Result type:    {'tuple (two-pass sentinel)' if ok else type(result).__name__}")

    if ok:
        _, catch_from, catch_to = result
        print(f"  Catch-up from:  {catch_from}")
        print(f"  Catch-up to:    {catch_to}")

        catchup_argv = list(argv) + ["--from", catch_from, "--to", catch_to, "--subfolder", "Daily"]
        print(f"\n  Pass 1 argv:    {catchup_argv}")
        print(f"  Pass 2 argv:    {argv or '(none = all periods)'}")

        # Verify Pass 1 produces the right plan
        from core.dates import resolve_fetch_plan
        plan1 = resolve_fetch_plan(from_date=catch_from, to_date=catch_to, subfolder_override="Daily")
        print(f"\n  Pass 1 plan:")
        print(f"    Fetch range:  {plan1.fetch_start} to {plan1.fetch_end}")
        for p in plan1.periods:
            print(f"    Period:       {p.label:30s} subfolder={p.subfolder:10s} tag={p.filename_tag}")

        p1_ok = (len(plan1.periods) == 1
                 and plan1.periods[0].subfolder == "Daily"
                 and str(plan1.periods[0].start_date) == catch_from
                 and str(plan1.periods[0].end_date) == catch_to)
        print(f"    Check: subfolder=Daily, range covers missed days: {PASS if p1_ok else FAIL}")

        # Verify Pass 2 produces all period files
        plan2 = resolve_fetch_plan(today=sim_now.date())
        print(f"\n  Pass 2 plan:")
        print(f"    Fetch range:  {plan2.fetch_start} to {plan2.fetch_end}")
        for p in plan2.periods:
            print(f"    Period:       {p.label:30s} subfolder={p.subfolder:10s} tag={p.filename_tag}")

        expected_subs = {"Daily", "MTD", "YTD", "This Week"}
        actual_subs = {p.subfolder for p in plan2.periods}
        p2_ok = expected_subs == actual_subs
        print(f"    Check: all subfolders present {expected_subs}: {PASS if p2_ok else FAIL}")
        if not p2_ok:
            print(f"    Missing: {expected_subs - actual_subs}")

        # Verify Pass 2 Daily covers yesterday (Mar 24)
        daily_period = [p for p in plan2.periods if p.subfolder == "Daily"][0]
        daily_ok = daily_period.start_date == date(2026, 3, 24) and daily_period.end_date == date(2026, 3, 24)
        print(f"    Check: Daily covers yesterday (2026-03-24): {PASS if daily_ok else FAIL}")
        if not daily_ok:
            print(f"    Actual: {daily_period.start_date} to {daily_period.end_date}")

        # Verify file paths would be correct
        print(f"\n  Expected output files:")
        print(f"    Pass 1: Direct Reports/Ordered Report/Daily/Ordered_Report_2026-03-23_to_2026-03-24.xlsx")
        print(f"    Pass 2: Direct Reports/Ordered Report/Daily/Ordered_Report_2026-03-24.xlsx")
        print(f"    Pass 2: Direct Reports/Ordered Report/MTD/Ordered_Report_MTD_2026-03-25.xlsx")
        print(f"    Pass 2: Direct Reports/Ordered Report/YTD/Ordered_Report_YTD_2026-03-25.xlsx")
        print(f"    Pass 2: Direct Reports/Ordered Report/This Week/Ordered_Report_Week_*.xlsx")

        all_ok = p1_ok and p2_ok and daily_ok
    else:
        print(f"  {FAIL}: Expected two-pass sentinel tuple, got: {result}")
        all_ok = False

    rb._SIMULATED_NOW = None
    os.unlink(log_path)
    return all_ok


def test_nightly_no_gap():
    """Nightly ordered (no args): ran yesterday -> no catch-up needed."""
    import universal_runbook as rb

    sim_now = datetime(2026, 3, 25, 23, 7, tzinfo=EASTERN)
    rb._SIMULATED_NOW = sim_now

    log_path = _make_run_log([
        {"timestamp": "2026-03-24 23:27:05", "report_name": "Ordered Report",
         "status": "SUCCESS", "args": ""},
    ])

    result = rb._maybe_inject_catchup_args([], "", log_path, "Ordered Report")
    ok = result == []

    print(f"\n--- Test: Nightly all-periods with NO gap ---")
    print(f"  Last success: 2026-03-24 (yesterday)")
    print(f"  Result:       {'unchanged (no catch-up)' if ok else result}")
    print(f"  {PASS if ok else FAIL}")

    rb._SIMULATED_NOW = None
    os.unlink(log_path)
    return ok


def test_daily_period_catchup():
    """--period daily schedule: missed 1 day -> single-pass --from/--to."""
    import universal_runbook as rb

    sim_now = datetime(2026, 3, 25, 8, 7, tzinfo=EASTERN)
    rb._SIMULATED_NOW = sim_now

    log_path = _make_run_log([
        {"timestamp": "2026-03-23 08:07:21", "report_name": "Ordered Report",
         "status": "SUCCESS", "args": "--salesman all --period yesterday"},
    ])

    merged = "--salesman all --period yesterday"
    argv = merged.split()
    result = rb._maybe_inject_catchup_args(argv, merged, log_path, "Ordered Report")

    ok = isinstance(result, list) and "--from" in result and "--subfolder" in result
    is_not_tuple = not isinstance(result, tuple)

    print(f"\n--- Test: --period yesterday with 2-day gap ---")
    print(f"  Last success:   2026-03-23")
    print(f"  Result:         {' '.join(result) if isinstance(result, list) else result}")
    print(f"  Single pass:    {PASS if is_not_tuple else FAIL} (should NOT be two-pass)")

    if ok:
        from core.dates import resolve_fetch_plan
        from_idx = result.index("--from")
        to_idx = result.index("--to")
        sub_idx = result.index("--subfolder")
        catch_from = result[from_idx + 1]
        catch_to = result[to_idx + 1]
        subfolder = result[sub_idx + 1]
        subfolder_ok = subfolder == "Daily"
        print(f"  From:           {catch_from}")
        print(f"  To:             {catch_to}")
        print(f"  Subfolder:      {subfolder} {PASS if subfolder_ok else FAIL}")

        plan = resolve_fetch_plan(from_date=catch_from, to_date=catch_to,
                                  subfolder_override=subfolder)
        print(f"  Plan periods:   {len(plan.periods)}")
        for p in plan.periods:
            print(f"    {p.label:30s} subfolder={p.subfolder}")
        ok = ok and subfolder_ok
    else:
        print(f"  {FAIL}: Expected list with --from/--to, got: {type(result).__name__}")

    rb._SIMULATED_NOW = None
    os.unlink(log_path)
    return ok and is_not_tuple


def test_nightly_3day_gap():
    """Nightly ordered (no args): missed 2 days (e.g. Shabbos+Sunday)."""
    import universal_runbook as rb

    sim_now = datetime(2026, 3, 25, 23, 7, tzinfo=EASTERN)
    rb._SIMULATED_NOW = sim_now

    log_path = _make_run_log([
        {"timestamp": "2026-03-22 23:27:05", "report_name": "Ordered Report",
         "status": "SUCCESS", "args": ""},
    ])

    result = rb._maybe_inject_catchup_args([], "", log_path, "Ordered Report")

    ok = (isinstance(result, tuple)
          and len(result) == 3
          and result[0] == rb._CATCHUP_THEN_NORMAL)

    print(f"\n--- Test: Nightly all-periods with 3-day gap ---")
    print(f"  Last success: 2026-03-22 (3 days ago)")

    if ok:
        _, catch_from, catch_to = result
        range_ok = catch_from == "2026-03-22" and catch_to == "2026-03-24"
        print(f"  Catch-up from:  {catch_from}")
        print(f"  Catch-up to:    {catch_to}")
        print(f"  Range correct:  {PASS if range_ok else FAIL}")
        print(f"  Two-pass:       {PASS}")
        ok = ok and range_ok
    else:
        print(f"  {FAIL}: Expected two-pass sentinel, got: {result}")

    rb._SIMULATED_NOW = None
    os.unlink(log_path)
    return ok


def test_last_7_days_catchup():
    """--period last_7_days: missed days -> single-pass widened window."""
    import universal_runbook as rb

    sim_now = datetime(2026, 3, 25, 8, 7, tzinfo=EASTERN)
    rb._SIMULATED_NOW = sim_now

    log_path = _make_run_log([
        {"timestamp": "2026-03-23 08:07:00", "report_name": "Ordered Report",
         "status": "SUCCESS", "args": "--customer 9300 9301 --period last_7_days"},
    ])

    merged = "--customer 9300 9301 --period last_7_days"
    argv = merged.split()
    result = rb._maybe_inject_catchup_args(argv, merged, log_path, "Ordered Report")

    is_list = isinstance(result, list)
    has_from = is_list and "--from" in result
    not_tuple = not isinstance(result, tuple)

    print(f"\n--- Test: --period last_7_days with 2-day gap ---")
    print(f"  Result:         {' '.join(result) if is_list else result}")
    print(f"  Single pass:    {PASS if not_tuple else FAIL}")
    print(f"  Has --from/--to:{PASS if has_from else FAIL}")

    if has_from:
        sub_idx = result.index("--subfolder") if "--subfolder" in result else None
        subfolder = result[sub_idx + 1] if sub_idx is not None else "(none)"
        subfolder_ok = subfolder == "This Week"
        print(f"  Subfolder:      {subfolder} {PASS if subfolder_ok else FAIL}")

    rb._SIMULATED_NOW = None
    os.unlink(log_path)
    return is_list and has_from and not_tuple


def main():
    print("=" * 70)
    print("  Two-Pass Catch-up Logic Simulation")
    print("=" * 70)

    results = []
    results.append(("Nightly two-pass (2-day gap)", test_nightly_two_pass()))
    results.append(("Nightly no gap", test_nightly_no_gap()))
    results.append(("--period daily catch-up", test_daily_period_catchup()))
    results.append(("Nightly two-pass (3-day gap)", test_nightly_3day_gap()))
    results.append(("--period last_7_days catch-up", test_last_7_days_catchup()))

    print("\n" + "=" * 70)
    print("  Summary")
    print("=" * 70)
    all_ok = True
    for name, ok in results:
        status = PASS if ok else FAIL
        print(f"  {status}  {name}")
        if not ok:
            all_ok = False

    print()
    if all_ok:
        print(f"  All {len(results)} tests passed.")
    else:
        failed = sum(1 for _, ok in results if not ok)
        print(f"  {failed}/{len(results)} tests FAILED.")
    print()
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
