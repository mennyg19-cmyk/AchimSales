# Grill notes — Beta app

Date: 2026-08-06

## Goal
Ship a **Beta reports page** so users learn the new GUI and report-run flow.
Long-term Beta **replaces Live**. Until then Live keeps scheduling and the rest
of the product surface.

## App map (locked)
| Surface | Role |
|---------|------|
| Live `/` | Original OData app; schedules/email/product features stay here |
| Test `/test` (v3) | SQL sandbox; **direct-link only** (no promo from Live) |
| Test-next `/test-next` | Rebuild preview; **retire** once Beta replaces it |
| Beta `/beta` | Reports menu only; Test look + rebuild-quality run path; hybrid data |

## Locked decisions
1. **Mount:** `/beta` on the same App Service. New tree from **`rebuild/`**
   (behavior) + **`v3/` look**. Not a fourth full fork of both codebases.
2. **Surface:** Reports front page only — menu → params → run → **on-screen
   results** → **Excel export**. No schedule, email, dashboard, or other
   Live features on Beta.
3. **Every report** is on Beta (including ones not SQL-signed yet).
4. **Data source per report:** SQL if signed off; else OData. Same UI either
   way (OData adapter shapes into the same table format — no Excel-only
   fallback for unsigned reports).
5. **Source switch:** Dev-only panel under **Live Settings** (stricter than
   beta access). Backed by **shared storage** (precious DB / equivalent) so
   phase two can read it from runbooks. Not a Beta-only in-memory flag.
6. **Access:** Link from Live only for `can_access_beta`. **Server hard-gate**
   — no permission ⇒ blocked even on direct `/beta` URL. Dev panel = separate
   stricter role.
7. **Schedules + SQL:** **Phase two.** Day one: Beta on-demand honors the
   switch; Live Azure Automation schedules stay OData. Do not treat a SQL
   flip as full source-of-truth until phase two, or accept schedule Excel can
   disagree with Beta on-screen.
8. **Retire `/test-next`** after Beta day-one is stable.

## Day-one done (validation)
Permissioned user: Live → Beta → every report runs → screen + export.
Signed-off → SQL; others → OData. Unpermissioned blocked. Dev can flip
sources in Live Settings. No schedule/email on Beta. Evidence: deployed
walkthrough checklist, once per report.

## Phase two (explicit defer)
Live `universal_runbook` / Azure schedules read the same source map and fetch
SQL when a report is flipped.

## Open / watch
- Exact report list on Beta = Live/Test registry keys (incl. CLO / item
  averages / aging backlog — aging stays disabled until built).
- OData adapters must produce Beta’s table shape without dragging Live’s
  Excel-first UX into Beta.
- Risk: flipping SQL before phase two ⇒ users see SQL on Beta, OData in
  scheduled email.

## Next concrete action
Enable `BETA_MOUNT_ENABLED=1` on Azure; grant Beta Access; smoke every report
on `/beta`. Retire `/test-next` after stable.

## Implementation note (2026-08-06)
Day-one code mounts **v3** at `/beta` (`is_beta`), not a rebuild fork — rebuild
only had 4 seeded reports. See DECISION-LOG. Branch: `cursor/beta-app-694b`.

## Auth fold (2026-08-06)
Beta **shares Live's session cookie** (`session` + `FLASK_SECRET_KEY`). No
separate `/beta/auth/callback`. Signed-in on Live → `/beta` works; otherwise
redirect to Live `/login?next=/beta/...`. WSGI mount kept for Test-look UI.
Branch: `cursor/beta-live-page-694b`.

---

# Grill notes — Salesman (+ remaining) sign-off vs TEST invoiced

Date: 2026-08-05

## Locked
1. Ground truth for money: **TEST invoiced** / `vw_Invoiced_Report`, not LIVE OData.
2. Already signed: ordered, invoiced, customer activity.
3. Salesman on `/test` uses **`monthly_salesman_yoy`** (`rpt.usp_monthly_salesman_yoy`), not `invoiced_order_charges`.
4. Sales basis: **Total Invoice** (SP). UI keeps 12 month tabs reshaped from the wide SP row.
5. After salesman: Number 4 (then CLO / Item Averages if needed).

## Validation (next)
- Deploy; confirm catalog id + column names via Azure hybrid.
- Reconcile salesman month/YTD totals to TEST invoiced Total Invoice by salesman+customer.
# Append â€” Beta additions grill (2026-08-06)

See full locked decisions: `.scratch/grill-notes-beta-additions.md`

Summary: Ordered-only default grouping; 48h resume + Keep 30d (cap 5);
salesman colors screen+Excel; filename token GUI; Last Order Export popup.

