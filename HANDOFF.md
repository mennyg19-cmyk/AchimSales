# Session Handoff

Last updated: 2026-07-24 ~14:02 local (UTC+3)

**Status:** ordered last_month DIFF (data-matched). Missing on /test mostly 2026-06-01; extras mostly 2026-06-30. Value gaps dominated by PO blank on /test + qty_released live=0 vs /test filled. Other three reports not run; tool still uncommitted.

## Working tree

- **Branch:** `rebuild-reports` (tracks `origin/rebuild-reports`, tip **`ef04067`**)
- **Repo:** `D:\Projects\Achim\AchimSales`
- **Prod URL:** https://reports.achimonline.com  
  - Live `/` = OData (freeze — phase out later)  
  - `/test` = v3 Reporting API / SQL-math  
  - `/test-next` = rebuild preview (out of parity scope for now)

## What's done (committed + pushed)

- **`ef04067`** — Remove Amazon Weekly as a named report (backup in `_history_backup/amazon_weekly-removed-2026-07-23/`, gitignored). Recreate schedule as:  
  `ordered --customer 9300 9301 --period last_7_days --email`
- **`529cb6b`** — Phone/Cursor cleanup: green-test Docker leftovers; DECISION-LOG on v3 vs rebuild keep-both

## What's done (NOT committed — next agent must commit if continuing)

Parity tool + docs (working tree dirty):

| Path | Role |
|------|------|
| `tools/parity/` | CLI: `python -m tools.parity` — includes `data_compare.py` key-matched comparer |
| `tools/__init__.py` | package marker |
| `tests/test_parity_report.py` | offline unit tests (6 passed) |
| `README.md`, `.env.example`, `DECISION-LOG.md` | PARITY_* docs + decision entry |
| `.scratch/grill-notes.md` | locked product decisions |
| `.scratch/run-state.md` | run checkpoint |
| `.scratch/parity/` | run outputs (gitignored via `.scratch/`) |

Also untracked: `.scratch/probe_cookies.py`, `.scratch/agent-run.ps1` (scratch only — may hold cookies; never commit).

## Locked product decisions (parity + rebuild)

From `.scratch/grill-notes.md` — do not reopen casually:

1. **Auth:** HTTP cookies (prod) or `--auth dev` (local). Not Playwright.
2. **Compare:** live `/` vs `/test` only. Five reports: ordered, invoiced, salesman, customer_activity, number_4.
3. **Defaults:** ordered `period=last_month`; invoiced `period=ytd`; number_4 `mode=both`; salesman/customer_activity `{}`.
4. **Comparer:** key-matched rows. Ignore formatting, column order, /test-only extra columns. Soft name-format (`Meir Grego` vs `Grego, Meir`) does not fail. Pattern summaries for missing rows / numeric gaps.
5. **Live:** no product changes (frozen baseline).
6. **Rebuild gate (strict order):**  
   a. Live↔/test math correct (intentional diffs accepted by Menny)  
   b. Then rebuild `/test` cleanly (mine git history for UX/design fixes)  
   c. Then re-check rebuilt Test vs **current** `/test` (math + features unchanged)  
   d. Only then replace current `/test`  
   e. Live cutover later

## Parity runs so far

### Invoiced YTD — SUCCESS (with DIFF)

- Folder: `.scratch/parity/20260724-043826/`
- Old cell-diff: **2603** / 4214 (noisy — layout/sort)
- Re-check with data matcher: still real gaps (~1219 hard), missing sheet `Audit - Reversals`, number diffs concentrated in totals/tariff/etc.

### Ordered last_month — SUCCESS (with DIFF)

- Folder: `.scratch/parity/20260724-070725/` (`ordered.md` + both xlsx)
- Hard diffs ~165k (mostly systematic column gaps, not random layout noise)
- **Row coverage patterns:**
  - Missing on /test: almost all dated **2026-06-01** (152/152 By Order; 198/257 Full Data)
  - Extra on /test: mostly dated **2026-06-30**
- **Value patterns:**
  - `po_number`: live has values, **/test always blank** (known SP stub)
  - `qty_released` / `released_dollars`: **live mostly 0**, /test filled
  - Also: order_date mismatches on thousands of matched orders; Summary remainder qty/price gaps

### Salesman / customer_activity / number_4

- Not run yet.

## How to run parity

```powershell
cd D:\Projects\Achim\AchimSales
# Fresh cookies if probe shows login redirect (503 = wait for Azure, not new cookies)

$env:PARITY_LIVE_COOKIE = "<session value>"
$env:PARITY_TEST_COOKIE = "<v3_session value>"
$env:PARITY_BASE_URL = "https://reports.achimonline.com"

python -m tools.parity --report ordered --param period=last_month -v --timeout 3600
python -m tools.parity --report salesman --report customer_activity --report number_4 -v --timeout 3600
```

Code: `tools/parity/clients.py`, `scenarios.py`, `data_compare.py`, `report.py`, `__main__.py`.  
`--param KEY=VALUE` overrides defaults for the selected reports.

**PowerShell:** put env + command in `.scratch/agent-run.ps1` and run with `-File`. **Never commit cookies.**

## What's next (ordered)

1. Wait until prod is not 503; probe cookies (login redirect = refresh; 503 = wait).
2. Run **ordered last_month**; read pattern section of `ordered.md`.
3. Run salesman / customer_activity / number_4.
4. Commit + push uncommitted `tools/parity` when Menny asks.
5. After math sign-off: git-history inventory of `/test` design fixes → clean Test rebuild → re-parity vs current test → replace `/test`.

## Open decisions

- When to commit `tools/parity`?
- Port `cursor/master-schedule-wizard-ca14` (old `webapp-cache` lineage) into `rebuild-reports`? Not done.
- Azure Automation jobs still named `amazon_weekly` must be switched manually to Ordered command (not done in Azure).

## Gotchas

- Live and `/test` use **different** cookies (`session` vs `v3_session`).
- `/test` POSTs need **CSRF** (`X-CSRF-Token`).
- HTTP 503 = Azure/app down — do not burn cookies or assume auth failure.
- Do **not** change live product code (freeze).
- Do **not** start Test rebuild until live↔test math is signed off.
- `codegraph status` before structural search; healthy index → no Grep-for-symbols.
- Deploy is `deploy.ps1` zip, not auto on push.

## Proof-of-read for next agent

Orient: this file → `.scratch/run-state.md` → `.scratch/grill-notes.md` → README parity section → `tools/parity/`.
