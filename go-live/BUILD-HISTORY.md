# BUILD-HISTORY — live v3 go-live regression map

**Model:** composer-2.5-fast / **Runner:** spawn  
**Scope:** `v3/` Flask app at https://reports.achimonline.com — not UI inventory (other agents).  
**Sources:** `git log --oneline -150` (150 commits; 80+ touch `v3/`), `GO-LIVE-DAY-REPORT.md`, `DECISION-LOG.md` (2026-09-02), graph backbone INDEX.

---

## Proof-of-read

**`go-live/README.md`** — Go-live inventory targets **live production `v3/`** only (Phase 0–1 rebuild protocol). Not the unfinished `/test-next` rebuild under `rebuild/`. Artifacts: graph backbone, auditor reports, `FEATURE-INVENTORY.md`, `GO-LIVE-TEST-LOG.md`, day report.

**`go-live/rebuild-audit/graph-backbone/INDEX.md`** — Dated 2026-09-02. Four digest areas: auth-admin, reports-excel, schedules-delivery, settings-dashboard-data. Five worker job types (`report.run`, export, `report.deliver`, `schedule.run`, dashboard refresh). Roles: admin | developer | manager | salesman; privileged = admin + developer. Beta shares Live session cookie; dashboard blueprint not on Beta.

**`GO-LIVE-DAY-REPORT.md`** — Plain-English day report for 2 Sep 2026. **22 PRs on `main` (#11–#32)**; **PR #33** (review/security fixes) pending merge at write time. Schema migrations **0017** (`users.sales_group`) and **0018** (drop `user_salesman_access` FK to `salesmen`). Production UI row edits not visible from git.

**`DECISION-LOG.md`** — **28 entries dated 2026-09-02** above older history (no archive marker in file). Top entry: inventory live v3, no from-scratch rebuild; test log on `cursor/go-live-verify-551b` to avoid Azure redeploy on markdown. Dominant themes: Users & access wins over Live cookie, developer-role trust boundary, report/schedule/Excel decisions shipped same day.

---

## Late additions (2 Sep 2026 — on `main`, PRs #11–#32)

Shipped the same day as go-live inventory; treat as **must exist** in any regression pass.

### Schema

| Migration | Effect |
|-----------|--------|
| `0017_user_sales_group.sql` | `users.sales_group` — raw D365 SalesGroup string for salesman logins |
| `0018_usa_drop_salesmen_fk.sql` | `user_salesman_access` no longer requires a `salesmen` row (customer-master groups) |

### Users & access

- Display-name rename (email unchanged); Entra/Live upsert fills blank name only
- SalesGroup dropdown on salesman role from `GET /api/admin/sales-groups` (not report-gated URL)
- Per-user **company views** flag; admins/developers bypass flag for create/edit/delete + schedule Default
- Admin **Save for** another user (named views without impersonation); Switch user merges Live directory + v3 users
- Auto-check salesman access when new login email matches active `salesmen` row

### Reports & saved views

- Salesman report: Salesman dropdown (post-fetch alias filter; **do not** send SalesGroup as `SalesmanName` to SP)
- Daily Ordered: group salesman → customer; company views store **no period**; By Customer = salesman-only groups; By Order = flat
- Ordered Summary: **Extended Price Cancelled** column
- Number 4: months before totals block; By Item dollars; ungrouped Default honoured in emailed workbooks
- Saved views panel: collapsed Company / My groups; company-view **Delete** for editors; `_isDuplicate` fix on apply
- Settings customer exclusions from same lookup as report picker (`/api/settings/customers`), scoped to salesman keys

### Schedules & delivery

- Personal schedules: full width; one shared grid with owner banner rows; CC/BCC for privileged (personal wizard + More → Schedule)
- Filename default `{Schedule}_{MM}-{DD}-{YYYY}` (existing templates unchanged; same-day reruns may overwrite)
- Named personal Customer Activity views schedulable **without** period (Default / company / custom from-to still blocked)
- Fail mail held until retry success can replace it (home-site extra delivery)
- Oversized mail: SharePoint/download link when Graph won't attach (including post-chunked-upload `webUrl` recovery)

### Excel export

- Ordered group footers: **do not sum Net Price** (Number 4 Avg/Book Price still sums)
- Nested header (blue) / footer (grey) shade ladders; contrast-aware text; grid + Excel share RGB
- Salesman bands coloured by **field tag**, not exported column index (hidden columns must not shift bands)
- Excel outline groups **added then rolled back** — no collapse gutter; innermost footer grey `#9CA3AF`

### Deploy / tooling (non-UI but gates release)

- Official branch **`main`**; Azure deploys **only from `main`** (`cursor/**` no longer auto-deploy)
- Agent Guardrails Semgrep scans **`v3/` only**; skips Django/noisy rules

---

## Bug fixes & workarounds (git-mined — regression-critical)

Grouped by subsystem. Includes pre–2 Sep fixes still load-bearing for production.

### Auth, session, trust boundary

| Fix | Regression test |
|-----|-----------------|
| Beta is site home; old Live at `/legacy`; shared `session` cookie (no second Microsoft login) | Login once; Beta routes work; `/legacy` serves old app |
| Live login must **not** overwrite v3 display name, role, SalesGroup, external flag, salesman access after first row exists | Rename/role change in Users & access sticks after Beta page refresh |
| Developer tools / Switch user require **DB `developer` row**, not `_dev` cookie | Demoted developer loses dev UI even if cookie lingered |
| Leftover impersonation after demotion → actor identity or logout | View-as then demote actor |
| Only developers assign developer role; nobody changes own role; Add user **409** on duplicate email | Admin cannot mint developer or wipe developer via Add user |
| Export download re-checks salesman scope after demotion | Start company export as admin, demote, download must fail |
| `/test` impersonation developer-only; session refresh logs out if actor not active developer | — |
| Developer first Live login creates row without logout bounce | New developer Entra sign-in |
| GET precious-repair **check only**; mutations POST + CSRF | GET cannot delete ghosts |
| Missing user on salesman/report-access → **404**, not SQLite 500 | — |
| `claim-once` schedule runner POST-only, exactly-one-row update | — |

### Reports & data correctness

| Fix | Regression test |
|-----|-----------------|
| Salesman filter: alias match after fetch, not SP `SalesmanName` = SalesGroup key | Filter returns rows for Reggie-style names |
| Ordered remainder/shipping from SP/catalog columns; stop inventing shipping $ when SP blank | Blank SP fields stay blank |
| Daily Ordered grouping/sort: salesman blocks consecutive; customer sort within salesman | Summary Excel one salesman block per rep |
| `_isDuplicate` on apply: do not put `generated_at` on `state.tabs` | Apply saved view — no pink banner |
| Preset salesman/Open status kept when dropdown still empty | Home presets |
| Run saved views / home presets instead of replaying last job | — |
| Ordered Fulfillment % coloured on rolled-up tabs | — |
| Invoiced: skip YTD fetch when output has no Commissions tab | Scheduled Invoiced without Commissions |
| Stop using `salesman_map.xlsx` for invoiced salesman identity | Invoiced salesman 029-class cases |
| NYC sales amount on first Summary row only | Sales by State |
| Reporting API timeout 300s for Ordered YTD | Full-year Ordered |
| Ordered memory cap for ~488k-row full-year run | — |

### Schedules & clock

| Fix | Regression test |
|-----|-----------------|
| Schedule run crash when `company_views` column missing | Old DB / migration edge |
| Boot seed must not restore **deleted** company schedules | Delete schedule, restart |
| Save and On does **not** run immediately | Toggle schedule on |
| Shabbos skip + havdalah catch-up (Beta + home-site makeup waits for clock) | Sabbath boundary |
| Job retry once before permanent fail; fail mail to test list on home schedule fail | Induced failure |
| Empty Daily Invoiced: SQL window includes end of day | Midnight boundary |
| SharePoint: no nested Direct Reports; dated subfolders allowed | Upload path |
| Text-only split mail after 3 MB Graph attachment skip merge | Large split mail |
| Do not resend test mail when Test folder upload failed | — |

### Mail & Graph / SharePoint

| Fix | Regression test |
|-----|-----------------|
| Skip Graph attachments > 3 MB; include download button / link in body | Number 4 ~13 MB |
| Chunked upload: GET `/items/{id}` for `webUrl` before createLink | Oversized Number 4 mail has link |
| Retry SharePoint downloads | Transient SP errors |

### Excel & export pipeline

| Fix | Regression test |
|-----|-----------------|
| Net Price not summed on group footers | Daily Ordered Excel footers |
| Salesman band colours follow field `band` tag | Default 2 hides Sort Number / Salesman |
| No Excel outline levels (rollback) | No +/- gutter |
| Background export + streaming openpyxl; export list cap applies scope **before** 15-item limit | Demoted user list |
| Drop removed tabs from scheduled workbooks | Tab visibility flags |
| Percent totals, hidden-group, clone fixes (export review) | — |

### Infrastructure & jobs

| Fix | Regression test |
|-----|-----------------|
| `precious.db` off `/home` SMB; refuse prod boot with DB on SMB | Job queue not stalled |
| Non-WAL journal allowed for SMB (legacy path) | — |
| Cap crash-recovery retries (OOM report must not crash-loop site) | — |
| Background owner file lock; gunicorn leader age | Multi-worker |
| Beta DB Litestream replica (settings survive recycle) | Recycle / redeploy |
| Restore live Beta-as-home after accidental `webapp-cache` deploy | Routing |

---

## Post-launch / pending at inventory time (PR #33)

Not on `main` when day report written; merge before treating as live. Automated: **633 passed, 1 skipped** (Flask test client, isolated sqlite — not browser).

**Security & login:** GET mutations blocked on precious-repair; Live adopt stops wiping v3 edits; shared active-developer check; impersonation cleanup; export scope on download; claim-once POST-only; admins cannot disable/delete developer (extends minting block).

**Accepted risks documented in day report:** Delete user removes v3 data only — valid Live cookie can recreate row; Disable blocks sign-in.

---

## Pre–2 Sep features still in production path

From older `v3/` commits in the -150 window — easy to miss in a “today only” test:

- **Sales by State** SQL-only home-site report (PR merge ~meeting-fix)
- **Company Default view** for every report + company views for Daily Ordered / Heshy Open Orders
- **3-step personal schedules** from named saved views; company wizard under Settings
- **Monthly salesman split** schedule (test inbox in test mode)
- **Email me** on report page; Commissions hidden from salesmen
- **Keep runs** / named export history; tiered export retention
- **Schedule test mode** with test email list
- **Personal OneDrive delivery** on Beta schedules path
- **Recent Reports** header link; exports from status line
- **Number 4** YTD tabs, group-by-item (later overridden for column order on 2 Sep)

---

## Go-live / rebuild test — do not regress (checklist)

Use as pass/fail gates after code or deploy changes. Each line is a known production pain point from git + decisions.

### P0 — security & identity

1. Users & access edits (name, role, SalesGroup, salesman access) survive Beta/Live login refresh
2. Admin cannot become developer via PUT or Add user; developer lifecycle developer-only
3. Demoted developer loses dev tools, `/test` impersonation, and stale export downloads
4. Precious-repair and schedule claim mutations require POST + CSRF
5. Impersonation cookie does not grant developer after demotion

### P0 — money & report truth

6. Net Price not totaled on Ordered group footers
7. Ordered remainder/shipping match SP; no invented shipping dollars
8. Salesman report filter works via alias match, not wrong SP parameter
9. Number 4 column order: months → totals block; By Item dollars; emailed Default ungrouped when saved that way

### P0 — schedules & mail

10. Named CA views without period appear on schedule list and run
11. Oversized workbook email includes working SharePoint/download link (chunked upload path)
12. Fail notice suppressed if retry succeeds; home-site makeup respects Shabbos clock
13. Personal schedule CC/BCC only for privileged; salesman still emails self only
14. Filename `{Schedule}_{MM}-{DD}-{YYYY}` on new schedules

### P1 — Excel & UI behaviour

15. Salesman Excel colour bands align with grid when columns hidden
16. Nested group greys/blues match grid; footer grey dark enough (`#9CA3AF` at 2-level)
17. Apply saved view without `_isDuplicate` error
18. Company views: privileged always; flag-gated for salesmen/managers; delete only when editor
19. Daily Ordered company views without period; By Customer / By Order grouping rules
20. Settings exclusions reject out-of-scope customers

### P1 — ops & resilience

21. Deploy from `main` only
22. Job queue on local precious DB (not SMB stall)
23. Graph >3 MB → link not silent failure
24. Deleted company schedules stay deleted after boot seed
25. Save and On waits for next scheduled time

---

## Git index (recent `v3/` — sample)

Last 150 repo commits include inventory doc commits; **~80** touch `v3/`. Notable hashes for bisect:

| Commit | Summary |
|--------|---------|
| `3cd59e2` | Stop Live login from wiping v3 user edits |
| `4247345` | Block GET mutations precious-repair; 404 unknown user access |
| `bdcc716` / `d929467` | Developer role boundary |
| `ffad173` | `_isDuplicate` saved view apply |
| `1768edf` | Net Price group totals |
| `0a53c84` | SharePoint link after chunked upload |
| `330d1bc` | Ordered shipping dollars |
| `07992a7` | company_views column missing crash |
| `8dd44ca` / `da69e7c` | precious.db off SMB |
| `70468bd` | Graph 3 MB attachment skip |
| `f1b8cc1` | Restore Beta-as-home |
| `785684c` | Shabbos skip + catch-up |

Full log: `git log --oneline -150 -- v3/` from repo root.

---

*Generated for live v3 go-live inventory. Update when PR #33 merges to `main` and Azure is green.*
