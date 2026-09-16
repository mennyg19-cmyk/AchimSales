"""Compare production workbooks: old layout_json vs assembled normalized views.

One SP/payload per view. Two xlsx builds (old JSON layout vs assemble). Diff
sheet names + cell values. Needs a precious.db copy and Reporting API access.

From v3/:

    PRECIOUS_DB_PATH=/path/to/precious.db \\
    REPORTING_API_BASE_URL=https://… \\
    REPORTING_API_KEY=… \\
    python -m tools.compare_view_workbooks

Optional: --out .scratch/view-workbook-compare/run1
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Allow `python -m tools.compare_view_workbooks` from v3/.
_V3 = Path(__file__).resolve().parents[1]
if str(_V3) not in sys.path:
    sys.path.insert(0, str(_V3))

from web.data.connection import Database
from web.data.migrate import migrate
from web.data.normalized_views import (
    assemble_layout,
    assemble_params,
    canonicalize_layout,
    project_from_legacy,
)
from web.delivery.layout import apply_layout, expand_clones
from web.reporting.export import build_workbook
from web.reporting.http_client import ReportingApiClient
from web.reporting.report_service import ReportService
from web.reporting.salesman_directory import SalesmanDirectory
from web.scheduling.company_layouts import DAILY_ORDERED_VIEW, HESHY_OPEN_VIEW

EASTERN = ZoneInfo("America/New_York")

# Locked Gate B fixture set (normalized-views.md).
FIXTURES = (
    {"label": "Daily Ordered", "kind": "company", "report_key": "ordered",
     "name": DAILY_ORDERED_VIEW, "fallback_period": "yesterday"},
    {"label": "Heshy Open Orders", "kind": "company", "report_key": "ordered",
     "name": HESHY_OPEN_VIEW, "fallback_period": None},
    {"label": "personal Ordered", "kind": "personal", "report_key": "ordered",
     "name": None, "fallback_period": None},
    {"label": "Number 4", "kind": "company", "report_key": "number_4",
     "name": None, "fallback_period": None},
    {"label": "ungrouped By Order", "kind": "personal", "report_key": "ordered",
     "name": None, "want_ungrouped_by_order": True, "fallback_period": None},
)


def _sheet_grid(xlsx_bytes: bytes):
    from web.delivery.workbook_parity import sheet_grid
    return sheet_grid(xlsx_bytes)


def _diff_sheets(old_sheets, new_sheets) -> list[str]:
    from web.delivery.workbook_parity import diff_sheet_grids
    return diff_sheet_grids(old_sheets, new_sheets)


def _xlsx(payload: dict, layout: dict) -> bytes:
    shaped = apply_layout(expand_clones(payload, layout), layout)
    return build_workbook(shaped, layout)


def _raw_legacy(conn, source: str, legacy_id: int) -> tuple[dict, dict]:
    """Read the dual-written JSON blobs directly (bypass live-read hydrate)."""
    row = None
    if source == "saved_reports":
        row = conn.execute(
            "SELECT params_json, layout_json FROM saved_reports WHERE id=?",
            (legacy_id,),
        ).fetchone()
    elif source == "company_views":
        row = conn.execute(
            "SELECT params_json, layout_json FROM company_views WHERE id=?",
            (legacy_id,),
        ).fetchone()
    elif source == "report_defaults":
        vr = conn.execute(
            "SELECT report_key FROM views WHERE legacy_source=? AND legacy_id=?",
            (source, legacy_id),
        ).fetchone()
        if vr is not None:
            row = conn.execute(
                "SELECT params_json, layout_json FROM report_defaults WHERE report_key=?",
                (vr["report_key"],),
            ).fetchone()
    if row is None:
        return {}, {}
    try:
        params = json.loads(row["params_json"] or "{}")
    except (TypeError, ValueError):
        params = {}
    try:
        layout = json.loads(row["layout_json"] or "{}")
    except (TypeError, ValueError):
        layout = {}
    return (
        params if isinstance(params, dict) else {},
        layout if isinstance(layout, dict) else {},
    )


def _pick_views(conn) -> list[dict]:
    """Resolve FIXTURES to concrete views rows present in this DB."""
    out: list[dict] = []
    used_ids: set[str] = set()
    for spec in FIXTURES:
        row = None
        if spec.get("want_ungrouped_by_order"):
            for cand in conn.execute(
                "SELECT v.id, v.kind, v.report_key, v.name, v.legacy_source, v.legacy_id"
                " FROM views v"
                " JOIN layout_tabs t ON t.view_id=v.id AND t.tab_key='by_order' AND t.has_view=1"
                " WHERE v.kind='personal' AND v.report_key='ordered'"
                " AND NOT EXISTS ("
                "   SELECT 1 FROM layout_tab_groups g WHERE g.tab_id=t.id)"
                " ORDER BY v.id"
            ):
                if cand["id"] not in used_ids:
                    row = cand
                    break
        elif spec.get("name"):
            row = conn.execute(
                "SELECT id, kind, report_key, name, legacy_source, legacy_id"
                " FROM views WHERE kind=? AND report_key=? AND name=?",
                (spec["kind"], spec["report_key"], spec["name"]),
            ).fetchone()
        elif spec["kind"] == "personal" and spec["report_key"] == "ordered":
            for cand in conn.execute(
                "SELECT id, kind, report_key, name, legacy_source, legacy_id"
                " FROM views WHERE kind='personal' AND report_key='ordered'"
                " ORDER BY id"
            ):
                if cand["id"] not in used_ids:
                    row = cand
                    break
        elif spec["report_key"] == "number_4":
            row = conn.execute(
                "SELECT id, kind, report_key, name, legacy_source, legacy_id"
                " FROM views WHERE report_key='number_4' AND kind IN ('company','default')"
                " ORDER BY CASE kind WHEN 'company' THEN 0 ELSE 1 END, name"
            ).fetchone()
        if row is None:
            out.append({"spec": spec, "missing": True})
            continue
        used_ids.add(row["id"])
        out.append({
            "spec": spec,
            "missing": False,
            "view_id": row["id"],
            "kind": row["kind"],
            "report_key": row["report_key"],
            "name": row["name"],
            "legacy_source": row["legacy_source"],
            "legacy_id": row["legacy_id"],
        })
    return out


def _run_params(assembled_params: dict, fallback_period: str | None) -> dict:
    params = dict(assembled_params or {})
    if fallback_period and not (
        params.get("period") or params.get("start_date") or params.get("from")
    ):
        params["period"] = fallback_period
    return params


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--precious", default=os.environ.get("PRECIOUS_DB_PATH", ""))
    ap.add_argument("--cache", default=os.environ.get("CACHE_DB_PATH", ""))
    ap.add_argument("--api-url", default=os.environ.get("REPORTING_API_BASE_URL", ""))
    ap.add_argument("--api-key", default=os.environ.get("REPORTING_API_KEY", ""))
    ap.add_argument("--out", default="")
    ap.add_argument("--timeout", type=float, default=300.0)
    args = ap.parse_args(argv)

    if not args.precious:
        print("Set PRECIOUS_DB_PATH or pass --precious", file=sys.stderr)
        return 2
    if not args.api_url or not args.api_key:
        print("Set REPORTING_API_BASE_URL + REPORTING_API_KEY (or --api-url/--api-key)",
              file=sys.stderr)
        return 2

    precious = Path(args.precious)
    cache = Path(args.cache) if args.cache else precious.parent / "cache-compare.db"
    out_dir = Path(args.out) if args.out else (
        Path(".scratch") / "view-workbook-compare"
        / datetime.now(EASTERN).strftime("%Y%m%d-%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    db = Database(precious, cache)
    migrate(db)
    project_from_legacy(db)

    client = ReportingApiClient(args.api_url, args.api_key, timeout=args.timeout)
    salesmen = SalesmanDirectory(client, db)
    service = ReportService(client, salesmen)

    results: list[dict] = []
    with db.precious() as conn:
        picks = _pick_views(conn)

    for pick in picks:
        label = pick["spec"]["label"]
        if pick.get("missing"):
            results.append({"label": label, "ok": False, "error": "view not in DB"})
            print(f"SKIP {label}: view not in DB")
            continue
        print(f"RUN  {label} ({pick['kind']} {pick['report_key']}/{pick['name']})…")
        with db.precious() as conn:
            raw_params, raw_layout = _raw_legacy(
                conn, pick["legacy_source"], int(pick["legacy_id"]))
            assembled_params = assemble_params(conn, pick["view_id"])
            assembled_layout = assemble_layout(conn, pick["view_id"])

        run_params = _run_params(
            assembled_params, pick["spec"].get("fallback_period"))
        try:
            builder = service.builder_for(pick["report_key"])
            payload = builder(run_params, None)
        except Exception as exc:
            results.append({"label": label, "ok": False, "error": str(exc)})
            print(f"FAIL {label}: report build: {exc}")
            continue

        payload = dict(payload)
        payload["report_key"] = pick["report_key"]
        old_bytes = _xlsx(payload, raw_layout)
        new_bytes = _xlsx(payload, assembled_layout)
        (out_dir / f"{label.replace(' ', '_').lower()}_old.xlsx").write_bytes(old_bytes)
        (out_dir / f"{label.replace(' ', '_').lower()}_new.xlsx").write_bytes(new_bytes)

        layout_match = canonicalize_layout(raw_layout) == canonicalize_layout(
            assembled_layout)
        old_sheets = _sheet_grid(old_bytes)
        new_sheets = _sheet_grid(new_bytes)
        notes = _diff_sheets(old_sheets, new_sheets)
        ok = not notes
        results.append({
            "label": label,
            "ok": ok,
            "view_id": pick["view_id"],
            "name": pick["name"],
            "report_key": pick["report_key"],
            "run_params": run_params,
            "layout_canonical_match": layout_match,
            "old_sheets": [n for n, _ in old_sheets],
            "rows": sum(len(t.get("rows") or []) for t in payload.get("tabs") or []),
            "diff": notes,
        })
        print(f"{'OK  ' if ok else 'DIFF'} {label}: "
              f"{results[-1]['rows']} grid rows, "
              f"sheets={results[-1]['old_sheets']}")

    lines = [
        f"# View workbook compare ({datetime.now(EASTERN).isoformat()})",
        "",
        f"DB: `{precious}`",
        f"API: `{args.api_url}`",
        "",
        "| View | Result | Rows | Layout JSON≡assemble |",
        "|---|---|---|---|",
    ]
    for r in results:
        if "error" in r and not r.get("ok"):
            lines.append(f"| {r['label']} | FAIL: {r['error']} | | |")
            continue
        mark = "MATCH" if r["ok"] else "DIFF"
        lines.append(
            f"| {r['label']} | {mark} | {r.get('rows', '')} | "
            f"{r.get('layout_canonical_match', '')} |"
        )
    lines.append("")
    for r in results:
        if r.get("diff"):
            lines.append(f"## {r['label']} diffs")
            lines.extend(f"- {n}" for n in r["diff"])
            lines.append("")
    (out_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / "results.json").write_text(
        json.dumps(results, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Wrote {out_dir / 'INDEX.md'}")
    return 0 if all(r.get("ok") for r in results if not r.get("missing")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
