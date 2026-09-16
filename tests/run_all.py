"""
Test runner for the scripts/ codebase.

Usage:
    python -m tests.run_all               Run all unit tests
    python -m tests.run_all --dry-run     Also run live dry-run smoke tests (requires D365 creds)
"""

import argparse
import subprocess
import sys


def run_pytest() -> int:
    """Run all pytest unit tests under tests/."""
    print("=" * 60)
    print("Running pytest unit tests")
    print("=" * 60)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent),
    )
    return result.returncode


def run_dry_run_smoke() -> int:
    """Run each report with --dry-run against live D365 (requires credentials)."""
    print("\n" + "=" * 60)
    print("Running --dry-run smoke tests against live D365")
    print("=" * 60)

    reports = ["ordered", "invoiced", "salesman", "number_4"]
    failures = 0
    for report in reports:
        print(f"\n--- {report} --dry-run ---")
        result = subprocess.run(
            [sys.executable, "run.py", report, "--period", "daily", "--dry-run"],
            cwd=str(__import__("pathlib").Path(__file__).resolve().parent.parent),
        )
        if result.returncode != 0:
            print(f"  FAILED (exit {result.returncode})")
            failures += 1
        else:
            print(f"  PASSED")

    return failures


def main():
    parser = argparse.ArgumentParser(description="Run all tests")
    parser.add_argument("--dry-run", action="store_true",
                        help="Also run live --dry-run smoke tests (requires D365 credentials)")
    args = parser.parse_args()

    exit_code = run_pytest()

    if args.dry_run:
        smoke_failures = run_dry_run_smoke()
        exit_code = max(exit_code, smoke_failures)

    print("\n" + "=" * 60)
    if exit_code == 0:
        print("ALL TESTS PASSED")
    else:
        print(f"TESTS FAILED (exit code {exit_code})")
    print("=" * 60)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
