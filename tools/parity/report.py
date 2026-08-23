"""Write human-readable parity diff reports (data-matched, not cell-position)."""

from __future__ import annotations

from pathlib import Path

from tools.parity.data_compare import DataComparisonResult, compare_workbooks_data


def compare_pair(
    live_path: Path,
    test_path: Path,
    *,
    tolerance: float = 0.01,
    max_examples: int = 50,
) -> DataComparisonResult:
    return compare_workbooks_data(
        live_path,
        test_path,
        tolerance=tolerance,
        max_examples=max_examples,
    )


def write_report(
    out_path: Path,
    *,
    report_key: str,
    params: dict,
    live_path: Path | None,
    test_path: Path | None,
    comparison: DataComparisonResult | None,
    error: str | None = None,
) -> None:
    lines = [
        f"# Parity: {report_key}",
        "",
        f"- Params: `{params}`",
        f"- Live file: `{live_path}`" if live_path else "- Live file: (missing)",
        f"- Test file: `{test_path}`" if test_path else "- Test file: (missing)",
        "",
        "_Compare mode: key-matched rows. Ignores formatting, column order, and "
        "columns that exist only on /test. Soft name-format diffs "
        "(e.g. `Meir Grego` vs `Grego, Meir`) do not fail._",
        "",
    ]
    if error:
        lines += ["## ERROR", "", error, ""]
    elif comparison is None:
        lines += ["## ERROR", "", "No comparison produced.", ""]
    else:
        sheet_bits = []
        for s in comparison.sheets:
            if s.status == "SKIP":
                sheet_bits.append(f"{s.sheet}=SKIP")
            else:
                sheet_bits.append(f"{s.sheet}={s.status}({s.hard_diff_count})")
        lines += [
            "## Summary",
            "",
            f"- Hard differences: **{comparison.total_diffs}**",
            f"- Missing sheets in /test: {comparison.missing_sheets_in_test or '(none)'}",
            f"- Extra sheets in /test (ignored): {comparison.extra_sheets_in_test or '(none)'}",
            f"- Per sheet: {', '.join(sheet_bits) or '(none)'}",
            f"- Result: **{'MATCH' if comparison.is_match else 'DIFFERENCES FOUND'}**",
            "",
            "## Patterns + detail",
            "",
            "```",
            comparison.summary(),
            "```",
            "",
            "_Live is the baseline. Review each difference: intentional product "
            "change (accept) vs bug (fix on /test)._",
            "",
        ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_index(out_dir: Path, rows: list[dict]) -> Path:
    path = out_dir / "INDEX.md"
    lines = [
        "# Live vs /test parity run",
        "",
        "| Report | Status | Diffs | Detail |",
        "|--------|--------|------:|--------|",
    ]
    for row in rows:
        lines.append(
            f"| {row['report']} | {row['status']} | {row.get('diffs', '—')} | "
            f"[open]({row['detail']}) |"
        )
    lines += ["", f"Output folder: `{out_dir}`", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
