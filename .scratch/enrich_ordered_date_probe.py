"""Reclassify ordered coverage diffs with SalesTableCDR fallback for missing HeadersV3."""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests
from dotenv import load_dotenv
from openpyxl import Workbook

load_dotenv()
from config.settings import get_client_id, get_client_secret, get_d365_env_url, get_tenant_id
from core.auth import get_d365_token

PARITY = Path(".scratch/parity/20260804-193031-postfix/ordered_line_date_probe")
PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 7, 31)


def dnorm(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return ""
    return s[:10] if "T" in s or len(s) >= 10 else s


def in_july(s: str) -> bool:
    try:
        d = date.fromisoformat(dnorm(s))
    except ValueError:
        return False
    return PERIOD_START <= d <= PERIOD_END


def main():
    probe = pd.read_csv(PARITY / "odata_header_vs_line_dates.csv")
    # Drop bogus Total row from report totals
    probe = probe[probe["sales_order"].astype(str).str.upper() != "TOTAL"].copy()

    blank = (
        probe["header_order_creation"].isna()
        | (probe["header_order_creation"].astype(str).isin(["", "nan"]))
    )
    missing_sos = sorted(probe.loc[blank, "sales_order"].astype(str).unique())
    print("SOs needing SalesTableCDR fallback:", len(missing_sos))

    env = get_d365_env_url().rstrip("/")
    if not env.lower().endswith("/data"):
        env += "/data"
    token = get_d365_token(get_tenant_id(), get_client_id(), get_client_secret(), get_d365_env_url())
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "OData-MaxVersion": "4.0",
        "OData-Version": "4.0",
    }
    cdr_by_so: dict[str, dict] = {}
    if missing_sos:
        filt = " or ".join(f"SalesId eq '{s}'" for s in missing_sos)
        r = requests.get(
            f"{env}/SalesTableCDREntities",
            params={
                "$filter": filt,
                "$select": "SalesId,SysCreatedDateTime,CreatedOn,SysDataAreaId,SalesStatus",
                "cross-company": "true",
            },
            headers=headers,
            timeout=120,
        )
        r.raise_for_status()
        for row in r.json().get("value") or []:
            so = str(row.get("SalesId") or "").strip()
            created = dnorm(row.get("SysCreatedDateTime") or row.get("CreatedOn"))
            cdr_by_so[so] = {
                "created": created,
                "status": row.get("SalesStatus"),
                "co": row.get("SysDataAreaId"),
            }
        print("SalesTableCDR hits:", len(cdr_by_so))

    buckets = Counter()
    rows_out = []
    for _, r in probe.iterrows():
        side = r["side"]
        so = str(r["sales_order"])
        h = dnorm(r.get("header_order_creation"))
        src = "SalesOrderHeadersV3"
        if not h and so in cdr_by_so:
            h = cdr_by_so[so]["created"]
            src = "SalesTableCDREntities"
        ln = dnorm(r.get("line_sys_created"))
        report = dnorm(r.get("report_order_date"))
        h_in = in_july(h) if h else False
        l_in = in_july(ln) if ln else False
        dates_differ = bool(h and ln and h != ln)
        tz = str(r.get("tz_edge") or "no")

        if not h:
            bucket = "no_header_any_entity"
        elif not ln:
            bucket = "no_line_created_odata"
        elif side == "test_only" and l_in and not h_in:
            bucket = "explained_line_in_header_out"
        elif side == "live_only" and h_in and not l_in:
            bucket = "explained_header_in_line_out"
        elif h_in and l_in:
            bucket = "both_in_period_other_cause"
        elif tz == "yes":
            bucket = "tz_edge"
        else:
            bucket = f"unexplained_{side}"

        # Refine: HeadersV3-missing but CDR header in July + line in July
        if src == "SalesTableCDREntities" and h_in and l_in and side == "test_only":
            bucket = "test_only_missing_from_live_odata_headers"

        buckets[f"{side}:{bucket}"] += 1
        rows_out.append({
            "side": side,
            "sales_order": so,
            "line_number": r["line_number"],
            "item": r["item"],
            "report_order_date": report,
            "header_created": h,
            "header_source": src if h else "",
            "line_sys_created": ln,
            "header_in_july": "yes" if h_in else "no",
            "line_in_july": "yes" if l_in else "no",
            "dates_differ": "yes" if dates_differ else ("no" if h and ln else ""),
            "bucket": bucket,
            "tz_edge": tz,
            "customer_account": r.get("customer_account", ""),
            "status": r.get("status", ""),
        })

    out = pd.DataFrame(rows_out)
    csv_path = PARITY / "odata_header_vs_line_dates_enriched.csv"
    out.to_csv(csv_path, index=False)

    wb = Workbook()
    ws = wb.active
    ws.title = "odata_probe"
    cols = list(out.columns)
    ws.append(cols)
    for row in rows_out:
        ws.append([row.get(c, "") for c in cols])
    ws2 = wb.create_sheet("summary")
    ws2.append(["bucket", "count"])
    for k, n in sorted(buckets.items(), key=lambda x: (-x[1], x[0])):
        ws2.append([k, n])

    nontz = out[out["tz_edge"] == "no"]
    explained = nontz[nontz["bucket"].isin([
        "explained_line_in_header_out", "explained_header_in_line_out"])]
    odata_gap = nontz[nontz["bucket"] == "test_only_missing_from_live_odata_headers"]
    both = nontz[nontz["bucket"] == "both_in_period_other_cause"]
    differ = nontz[nontz["dates_differ"] == "yes"]

    ws2.append([])
    ws2.append(["non_tz_rows", len(nontz)])
    ws2.append(["explained_by_line_vs_header_date_gate", len(explained)])
    ws2.append(["test_only_missing_from_live_HeadersV3_but_CDR_in_july", len(odata_gap)])
    ws2.append(["both_in_period_other_cause", len(both)])
    ws2.append(["header_ne_line_created", len(differ)])
    xlsx_path = PARITY / "odata_header_vs_line_dates_enriched.xlsx"
    wb.save(xlsx_path)

    print(f"\nWrote {csv_path}")
    print(f"Wrote {xlsx_path}")
    print("\n=== BUCKETS ===")
    for k, n in sorted(buckets.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {k}: {n}")
    print(f"\nnon-TZ: {len(nontz)}")
    print(f"  date-gate explained (line later / header earlier): {len(explained)}")
    print(f"  TEST-only because LIVE HeadersV3 misses SO (CDR header in July): {len(odata_gap)}")
    print(f"  both dates in July (other cause): {len(both)}")
    print(f"  header date != line created: {len(differ)}")

    # Fractional live_only
    live_both = out[(out.side == "live_only") & (out.bucket == "both_in_period_other_cause")]
    frac = live_both[live_both["line_number"].astype(str).str.contains(r"\.", regex=True)]
    print(f"\nlive_only both-in-period: {len(live_both)}; fractional LineNum: {len(frac)}")

    verdict = PARITY / "LINE_DATE_VERDICT.md"
    verdict.write_text(
        f"""# Ordered Full Data — line vs header date probe

Period: 2026-07-01 … 2026-07-31 (parity run `20260804-193031-postfix`).

## Exports

| File | What |
|------|------|
| `full_data_coverage_diffs.xlsx` | 264 live_only + 704 test_only Full Data lines |
| `odata_header_vs_line_dates_enriched.xlsx` | Per-line OData header + line created dates + bucket |

## OData fields

- Header create: `SalesOrderHeadersV3.OrderCreationDateTime` (fallback: `SalesTableCDREntities.SysCreatedDateTime` when HeadersV3 returns nothing)
- Line create: `SalesLineCDREntities.SysCreatedDateTime`

## Does “lines added after SO date” reconcile the coverage diffs?

**Partly — only a small slice.**

| Bucket (non-TZ) | Count | Meaning |
|-----------------|------:|---------|
| `explained_line_in_header_out` | {len(explained[explained.bucket=='explained_line_in_header_out']) if len(explained) else 0} | Header created **outside** July; line created **in** July → TEST keeps, LIVE drops. **This is the hypothesis.** |
| `test_only_missing_from_live_odata_headers` | {len(odata_gap)} | SO not returned by `SalesOrderHeadersV3` at all (LIVE blind), but `SalesTableCDR` says header was created **in July** and lines are in July. **Not** a line-later-than-header story — LIVE OData entity gap. |
| `both_in_period_other_cause` | {len(both)} | Header and line both in July. Mostly **live_only fractional LineNums** (delivery schedule / split lines) that TEST does not emit. |
| TZ edge (`tz_edge=yes`) | {(out.tz_edge=='yes').sum()} | Report OrderDate on month edge vs UTC OData day (e.g. report 2026-07-31, OData 2026-08-01). |

### Clear date-gate examples (hypothesis true)

Only **{len(explained[explained.bucket=='explained_line_in_header_out']) if len(explained) else 0}** lines, e.g. ORD00863771 / ORD00865884 / ORD00865989 — header late June, lines added in July.

### What this means for signing off TEST ordered

- The **desired rule** (filter by **line created date**) is confirmed on the handful of true late-add lines.
- Most **test_only** volume in this run is **not** explained by that rule. The big pile is orders LIVE never sees via `SalesOrderHeadersV3` even though CDR/SQL has them in July.
- Most **live_only** volume is **fractional line numbers** with matching July dates — a line-identity / delivery-schedule difference, not a date gate.

**Recommendation:** do **not** treat this probe alone as a full sign-off that “all ordered diffs are late lines.” It does support that TEST’s line-created-date gate is the right product rule for late-added lines; remaining gaps need a separate call (accept LIVE OData holes + fractional-line omission, or chase them).

""",
        encoding="utf-8",
    )
    print(f"\nWrote {verdict}")


if __name__ == "__main__":
    main()
