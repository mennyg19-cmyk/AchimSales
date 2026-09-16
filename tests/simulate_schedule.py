"""
Simulate the Shabbos/Yom Tov guard and catch-up logic for every scheduled
timeslot across a date range.

Part 1 (guard table): shows SKIP / RESCHEDULE / RUN for each slot.
Part 2 (catch-up):    for the first RUN after each melacha block, shows what
                      catch-up parameters would be injected.

Usage:
    python tests/simulate_schedule.py                           # next 21 days
    python tests/simulate_schedule.py 2026-04-01 2026-04-12     # custom range
    python tests/simulate_schedule.py 2026-04-01 2026-04-12 -v  # verbose
"""

import csv
import sys
import os
import tempfile
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "runbooks"))

EASTERN = ZoneInfo("America/New_York")

SCHEDULE_SLOTS = [
    ("05:00", "Nightly invoiced/number4", "", "Invoiced Report"),
    ("09:00", "Salesman invoiced",        "--salesman all --period yesterday", "Invoiced Report"),
    ("09:00", "Salesman ordered",         "--salesman all --period yesterday", "Ordered Report"),
    ("09:00", "Customer daily ordered",   "--customer 48999 917 2267 --period daily", "Ordered Report"),
    ("23:00", "Nightly ordered",          "", "Ordered Report"),
]


def _colour(text, code):
    try:
        if not sys.stdout.isatty():
            return text
    except Exception:
        return text
    return f"\033[{code}m{text}\033[0m"


def run_guard_simulation(start_date: date, end_date: date, verbose: bool = False):
    """Part 1: guard table showing SKIP/RESCHEDULE/RUN per slot."""
    import universal_runbook as rb

    current = start_date
    prev_date = None

    header = f"{'Date':12s} {'Time':6s} {'Day':4s} {'Schedule Label':28s} {'Melacha?':10s} {'Reason':22s} {'Action':12s} {'Havdalah':22s}"
    print()
    print("=" * len(header))
    print("  PART 1: Shabbos / Yom Tov Guard Simulation")
    print(f"  Range: {start_date} to {end_date} (Eastern)")
    print("=" * len(header))
    print()
    print(header)
    print("-" * len(header))

    while current <= end_date:
        for time_str, label, extra_args, _ in SCHEDULE_SLOTS:
            hour, minute = map(int, time_str.split(":"))
            sim_dt = datetime(current.year, current.month, current.day,
                              hour, minute, tzinfo=EASTERN)

            rb._SIMULATED_NOW = sim_dt
            is_assur, reason, havdalah_dt = rb._is_melacha_time()
            action = rb._classify_guard_action(extra_args) if is_assur else "RUN"

            day_abbr = current.strftime("%a")

            if is_assur:
                status_str = _colour("ASSUR", "31")
                action_str = _colour(action.upper(), "33" if action == "reschedule" else "31")
            else:
                status_str = _colour("mutar", "32")
                action_str = _colour("RUN", "32")

            havdalah_str = havdalah_dt.strftime("%a %m/%d %I:%M%p") if havdalah_dt else ""

            if prev_date and current != prev_date:
                print()

            print(f"{current!s:12s} {time_str:6s} {day_abbr:4s} {label:28s} {status_str:>19s} {reason:22s} {action_str:>21s} {havdalah_str:22s}")
            prev_date = current

            if verbose and is_assur:
                print(f"{'':12s} {'':6s} {'':4s}   args: {extra_args or '(none)'}")

        current += timedelta(days=1)

    rb._SIMULATED_NOW = None
    print()


def run_catchup_simulation(start_date: date, end_date: date):
    """Part 2: simulate catch-up parameters for first RUN after each melacha block.

    Builds a synthetic run_log.csv incrementally: each slot writes its outcome
    AFTER the catch-up check so the current slot never reads its own result.
    """
    import universal_runbook as rb

    LOG_COLS = ["timestamp", "report_name", "status", "duration_sec",
                "rows_output", "files_uploaded", "args", "error"]

    log_path = os.path.join(tempfile.gettempdir(), "sim_run_log.csv")
    with open(log_path, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=LOG_COLS).writeheader()

    print("=" * 130)
    print("  PART 2: Catch-up Parameter Simulation")
    print("  Shows what args would be injected for the first RUN after each skip block")
    print("=" * 130)
    import logging
    logging.getLogger("universal_runbook").setLevel(logging.WARNING)

    print()
    print(f"{'Date':12s} {'Time':6s} {'Schedule Label':28s} {'Original Args':40s} {'Catch-up Result'}")
    print("-" * 130)

    prev_status: dict[tuple, str] = {}

    current = start_date
    while current <= end_date:
        for time_str, label, extra_args, display_name in SCHEDULE_SLOTS:
            hour, minute = map(int, time_str.split(":"))
            sim_dt = datetime(current.year, current.month, current.day,
                              hour, minute, tzinfo=EASTERN)
            rb._SIMULATED_NOW = sim_dt
            is_assur, reason, _ = rb._is_melacha_time()

            slot_key = (time_str, label)
            was_skipped = prev_status.get(slot_key) == "SKIPPED"
            ts = sim_dt.strftime("%Y-%m-%d %H:%M:%S")

            if not is_assur and was_skipped:
                merged_args = extra_args
                argv = merged_args.split() if merged_args else []
                result = rb._maybe_inject_catchup_args(
                    argv, merged_args, log_path, display_name)

                # Handle two-pass sentinel tuple for no-period runs
                is_two_pass = (isinstance(result, tuple)
                               and len(result) == 3
                               and result[0] == rb._CATCHUP_THEN_NORMAL)

                if is_two_pass:
                    _, catch_from, catch_to = result
                    pass1_str = f"--from {catch_from} --to {catch_to} --subfolder Daily"
                    pass2_str = extra_args or "(all periods)"
                    result_display = _colour(f"TWO-PASS: [{pass1_str}] + [{pass2_str}]", "33")
                    logged_args = f"[catchup: {pass1_str}] + [normal: {pass2_str}]"
                else:
                    result_argv = result if isinstance(result, list) else argv
                    result_str = " ".join(result_argv)
                    if result_argv != argv:
                        result_display = _colour(result_str, "33")
                    else:
                        result_display = result_str or "(no change)"
                    logged_args = result_str

                print(f"{current!s:12s} {time_str:6s} {label:28s} {extra_args or '(none)':40s} {result_display}")

                with open(log_path, "a", newline="", encoding="utf-8") as f:
                    csv.DictWriter(f, fieldnames=LOG_COLS, extrasaction="ignore").writerow({
                        "timestamp": ts, "report_name": display_name,
                        "status": "SUCCESS", "args": logged_args,
                    })
            elif is_assur:
                with open(log_path, "a", newline="", encoding="utf-8") as f:
                    csv.DictWriter(f, fieldnames=LOG_COLS, extrasaction="ignore").writerow({
                        "timestamp": ts, "report_name": display_name,
                        "status": "SKIPPED", "args": extra_args, "error": reason,
                    })
            else:
                with open(log_path, "a", newline="", encoding="utf-8") as f:
                    csv.DictWriter(f, fieldnames=LOG_COLS, extrasaction="ignore").writerow({
                        "timestamp": ts, "report_name": display_name,
                        "status": "SUCCESS", "args": extra_args,
                    })

            prev_status[slot_key] = "SKIPPED" if is_assur else "SUCCESS"

        current += timedelta(days=1)

    rb._SIMULATED_NOW = None
    os.unlink(log_path)
    print()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    if len(args) >= 2:
        start = date.fromisoformat(args[0])
        end = date.fromisoformat(args[1])
    elif len(args) == 1:
        start = date.fromisoformat(args[0])
        end = start + timedelta(days=21)
    else:
        start = datetime.now(tz=EASTERN).date()
        end = start + timedelta(days=21)

    run_guard_simulation(start, end, verbose=verbose)
    run_catchup_simulation(start, end)


if __name__ == "__main__":
    main()
