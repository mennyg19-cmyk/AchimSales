# REBUILD-PLAN — brother’s internals, our look, our features

**Old app (WHAT + LOOK):** `v3/` and https://reports.achimonline.com  
**New app (HOW):** `app/` FastAPI + Jinja + copied v3 CSS + Tabulator  
**Architecture:** locked in `app/BROTHER-STACK-REBUILD.md`. No stack debate. Skip grill.  
**Production:** do not deploy over `achim-sales-reports` / reports.achimonline.com until Menny signs off. New Azure Web App first, DNS last. Never push this rebuild to AchimSales `main` until cutover.

Proof this plan covers the inventory: every P/S/I/F/D ID below is claimed by exactly one slice. Drops are explicit.

Frame: every **home-site** feature is preserved except locked DROPs (D1–D8). Visual = current v3 (pixel-matched shell/CSS/Tabulator). Internals = JSON contract + doorway, not a Flask port.

---

## Structural improvements (why this is a rebuild)

1. One site, one process — no four mounts (F1, D1).
2. UI binds to `data.tabs.*.rows` — no `report_engine` god module (F2, I2).
3. Sales facts from the office Reporting API only (I1). SQLite = users/views/schedules/jobs.
4. Own Entra; magic link only for active externals (F3, P1, Q8).
5. Same CSS tokens and Tabulator theming so it is not the beige/green AG Grid demo (S3, S4, D6).

---

## BUILD-HISTORY prevention (from live `v3/` pain, not leftover Flask)

| Pain | Prevention in this app |
|---|---|
| Always On GET `/` 401 | P2.2: 200 for User-Agent AlwaysOn |
| Explorer wiping WTD / JSON copies | Views as tables; do not overlay empty Default params on boot |
| Stuck “Running” after recycle | Abandon orphans on boot (P10.3) |
| Huge Excel OOM | Companion files / flatten high-cardinality groups (later export slice) |
| Pointing API at the website | Config refuse if base URL host is reports.achimonline.com (I1) |
| CI hitting the office | Tests mock doorway (I4) |
| Secrets in git | `.env` gitignored; no key in sample JSON |

---

## Slices

### Slice 1 — Shell + mock Invoiced + Tabulator (this delivery)

**Preview required.** Dev/preview login only (P1.4). Looks like live login (P1 card).

| Todo | Covers | Old reference |
|---|---|---|
| 1.1 FastAPI app, `/healthz`, AlwaysOn `/`, `/beta` 302, fail-closed prod flag | P2.1 P2.2 P13.1 I6 | `v3/web/blueprints/health.py` |
| 1.2 Copy v3 `main.css` tokens/shell/pages + icons | S3 S4 S5 P4.29 | `v3/web/static_src/css/*`, `static_dist/css/main.css` |
| 1.3 Login page (Achim User Login + External modal look) | P1 P1.2 (look) P1.4 | `login.html` live screenshot |
| 1.4 Signed-in header + bottom nav (Reports / Schedules / Settings) | S1 S2 D5 | `base.html` |
| 1.5 Reports home cards (Invoiced works; others labeled later-slice, Aging coming soon) | P3.1–P3.11 P3.14 | `reports_list.html` |
| 1.6 Invoiced page: filters chrome + Tabulator bound to mock `data.tabs` | P4.1 P4.3 P4.4 P4.10 P4.18 P4.19 P4.I1–P4.I5 S4 | `report_view.html`, sample JSON |
| 1.7 Theme cycle (4 themes) persisted | P4.29 P6.2 | `main.ts` |
| 1.8 Settings You: profile + theme | P6.1 P6.2 | `settings.html` |
| 1.9 Tests mock JSON; no office call | I2 I4 | sample JSON |

**Not in slice 1 (still KEEP, later slice):** Entra, magic-link send, live doorway, other reports’ data, views/Keep/export/email/schedules/People/Graph.

### Slice 2 — Live doorway Invoiced (admin)

P4.I8 P4.I9 P4.10 P4.16 I1 I4 — last-7-days smoke, 120s+ timeout, testers admin until salesman map. **Ask Menny for the 44-char key; never commit it.**

### Slice 3 — Remaining reports via `data.tabs`

P3.3–P3.10 P4.O* P4.S1 P4.N1 P4.C1 P4.A1 P4.ST P5.* — thin tab assembler until SQL supplies Open$/Fulfillment/YTD/item averages.

### Slice 4 — People, roles, salesman scope

P7.* P1.5 P4.27 P4.28 P6.4 P6.5 — block live Invoiced salesman role on F5 until Menny maps.

### Slice 5 — Saved/company views, Keep, Recent Reports

P3.12 P3.13 P4.12–P4.14 P4.21–P4.26 P4.22 S6 I3

### Slice 6 — Schedules, Shabbos, run logs

P8.* P9.* P10.* P6.7–P6.9 P4.14 — not Automation (D3).

### Slice 7 — Graph mail + SharePoint/OneDrive

P4.11 P4.24 P8.4 P8.6 I5 P4.23 (Excel)

### Slice 8 — Entra + magic link (real auth)

P1.1 P1.2 P1.3 P1.6 P7.8 — no Live cookie.

### Slice 9 — Developer tools + explorer

P6.10 P11.* P4.15 P12.* — **not** P6.11 OData picker (D2).

### Slice 10 — New Azure Web App + Menny click-through

P13.2 P13.3 I6 I7 — DNS last. Production merge = Premier review. Not AchimSales `main` until he says cut over.

---

## ID coverage (no orphans)

| IDs | Slice |
|---|---|
| P1 (look), P1.4, P2.*, P3.1–P3.11, P3.14, P4.1/3/4/10/18/19/29, P4.I1–I5, P6.1–P6.2, S1–S5, P13.1, I2, I4, I6 (preview) | 1 |
| P4.I8–I10, P4.16, I1 | 2 |
| P3.3–P3.10 rest, P4.O*, P4.S1, P4.N1, P4.C1, P4.A1, P4.ST, P5.* | 3 |
| P7.*, P1.5, P4.27–28, P6.4–6 | 4 |
| P3.12–13, P4.12–14, P4.21–26, S6, S7 | 5 |
| P8.*, P9.*, P10.*, P6.7–9 | 6 |
| P4.11, P4.23–24, P8.4/6, I5 | 7 |
| P1.1–1.3, P1.6, P7.8 | 8 |
| P6.10, P11.*, P4.15, P12.*, P4.2, P4.17, P4.30 | 9 |
| P13.2–3, I6 prod, I7, I8 | 10 |
| D1–D8, F1–F6, P6.11, P8.15–16, F1 dashboard | locked DROP / to-fix, not built as features |

P4.I6–I7 (Audit / Totals by Salesman) land with slice 3 assembler when `raw` has the flags.

---

## Slice 1 expected (written before build)

1. Open `/login` — same card as live: Sales Reports, Achim User Login, External Rep Login, blue primary, light gray page.
2. Achim User Login (preview) → Reports home with v3 header + bottom nav.
3. Theme button cycles four themes; page tokens change.
4. Open Invoiced → filters row + Run report loads mock JSON into Tabulator tabs (Full Details, Credits, Invoices, Summary, Commissions).
5. `/healthz` is `{"status":"ok"}`. `/beta` redirects to `/`.
6. Tests do not call the office API.
