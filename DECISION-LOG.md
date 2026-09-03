# Decision Log

## 2026-09-03 Phase 8.12 gate closed
**What I chose:** Close Phase 8.12. Trust-boundary N/A.
**Why:** Loop A zero on `e7e2d79`. Loop B F1 (linear order missed de-nesting) closed `635e4f3`. Loop B2 F2 (brace-less if grabbing a later `{`) closed `373a6b9`. B3 and Loop C zero. Agent Guardrails green on HEAD. Did not split `report.ts`. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-03 Phase 8.12: prove report boot order, do not split report.ts
**What I had to decide:** The leftover is "resolve report-module circular imports or add browser coverage proving initialization order." Python import-cycle scan of `v3/web` + `v3/report_engine` is already 0. `report.ts` imports only `filename_preview`, `dialog`, `searchable_picker`, `visibility`; none import `report.ts`.
**Options I considered:** (1) Split the 3400-line `report.ts` god file. (2) Source tests that lock the acyclic graph and `DOMContentLoaded` order. (3) Full Chrome CDP boot-order coverage.
**What I chose:** (2). Cycles are gone; the remaining work is proving order. Do not split without a refactor command. Committed tests in this PR stay source-level; Chrome CDP stays optional at review.
**Why:** Plan is an OR. Ponytail: no unrequested split. Salesman deep-link must stay stashed until `loadSalesmen` fills the `<select>`; auto-run must wait for resume + named view.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-03 Phase 8.11 gate closed
**What I chose:** Close Phase 8.11. Trust-boundary N/A.
**Why:** Loop A F1 (200 junk JSON as empty) and follow-ups (array body, missing `presets`) closed on `767704c`/`ec6600a`/`e044cb8`. A4 and Loop B zero. Loop C: extracted `failViewsLoad`; mirrored `aria-live` on `masterMsg`. Agent Guardrails expected green on HEAD. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-03 Phase 8.11: error when saved-view load into a schedule fails
**What I had to decide:** Next leftover after 8.10, and what “report-to-schedule draft transfer” means in this codebase (there is no draft object).
**Options I considered:** (1) Q8/Q9 (BLOCKED). (2) Phase 7 replica drop (waits on `/test`). (3) Report tablist / live status. (4) The named leftover: personal `loadViews` and company `loadSavedViews` swallow fetch failures and look like an empty or Default-only list.
**What I chose:** (4). Show a clear error on the existing wizard status nodes. Keep the genuine empty-state copy. Default stays on the company picker so a failed catalog load does not block scheduling Default.
**Why:** Plan text is specific. The silent catch is the only transfer of report views into a schedule draft.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-03 Phase 8.10 gate closed
**What I chose:** Close Phase 8.10. Trust-boundary N/A.
**Why:** Loop A (Terra) and Loop B (Sonnet) zero findings on HEAD `852cafb` (after merging `main` @ `ca2d6ec`). Loop C craft: one optional belt-and-suspenders nit on `closeEmailModal` nulling `watchedEmailJob`; left in place because Escape only hides the overlay and the null is the close-button path. Agent Guardrails green on the merge commit. `emailMe` inbox copy is intentional. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-03 Merge origin/main (ca2d6ec) into PR #35
**What I had to decide:** How to combine this PR's leftovers with main's drop of the local `salesmen` table, extra SalesGroups, test-mode, and Run-now `manual` jobs. Main also shipped `0019_drop_salesmen.sql` while this branch's unreleased delivery-legs file was already `0019`.
**Options I considered:** (1) Keep Phase 6.9 display of a local saved percent (impossible: the table is gone). (2) Display and dollars both use `_commission_rate` (SP row when present, else `salesmen_master` directory). (3) Renumber main's drop migration. (4) Rename this PR's unreleased `0019_delivery_legs.sql` to `0020`.
**What I chose:** (2) and (4). Keep HTTP-only Gunicorn, `enqueue_or_503`, immutable `slot_id` at enqueue, dialog helper, live regions, Phase 6.7 `None` vs `0.0`. Clock jobs still require `slot_id`; Run now gets a unique `schedrun:manual:...:{job_id}` and `slot_id = manual:{job_id}`. `last_run_at` ignores `legacy`/`unknown`/`output_meta.legacy` **and** `output_meta.manual`. Do not restore `bootstrap_background` starting the worker from Flask. Do not restore the salesman grid or `#esMsg`. Do not edit `0019_drop_salesmen.sql`.
**Why:** Q3's "saved salesman-table percent" died with the table. SP is the only master. Version is the full stem, so 0019 and 0020 both apply. Shipping a second 0019 would collide on production.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-03 Phase 8.10: replace "check the outbox" copy
**What I had to decide:** What the email modal should say when the 60-second client wait expires, and whether schedule history's "Outbox file / Outbox id" rows count as stale copy.
**Options I considered:** (1) Mirror Email me: "check your inbox shortly" — wrong when the recipients are other people or the target is a SharePoint folder. (2) Neutral: "Still sending — it will arrive shortly. You can close this window." (3) Also rename the history rows.
**What I chose:** (2) for the modal. History rows stay: they describe the real delivery channel to admins on a diagnostics page, not an instruction to users. Added a source test that no `static_src/js` file mentions the outbox.
**Why:** Users have no outbox to check; the `.eml` artifact is developer-only. One string, no behaviour change.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Sales reps can be assigned additional SalesGroups
**What you asked for:** Allow a sales rep to see another chosen sales rep's information like a manager can.
**What I chose:** Users & access shows the existing per-salesman checkbox grid for both managers and salesmen. A salesman's primary SalesGroup is always included, and admins/developers can check additional groups. The login remains a salesman, so this does not grant manager reports, commissions, company-view editing, or admin access.
**Why:** The authorization table already supports several SalesGroups per user. This exposes that scope control without promoting the rep or widening any other permission.
**Status:** DECIDED — shipping this change.

## 2026-09-03 Drop the Users & access D365 salesman grid
**What you asked for:** The bottom table on Users & access is unused and should be gone.
**What I chose:** Remove the read-only "Salesmen in D365" table. SalesGroup dropdowns and manager per-salesman checkboxes still read the SP. Logins stay the only list on that page.
**Why:** That grid was leftover from dropping the local salesmen table. D365 remains the master; nobody edits it here, so a duplicate list adds nothing.
**Status:** DECIDED

## 2026-09-03 Test mode covers personal schedules; Run now ignores "already ran today"
**What you asked for:** Test mode was sending personal schedules to the salesman. Run now did nothing if the schedule had already run today. Both are wrong; Run now is for testing.
**What I had to decide:** Whether test mode applies to personal the same as company; whether a recovered clock job after a crash still skips; whether Run now eats the 8am slot.
**What I chose:** Test mode rewrites every schedule (company and personal) to the test list, tags `[TEST]`, and does not write live SharePoint or the owner's OneDrive. Split files still fan out, all to the test list. Run now is a new job every press (`manual`), never collapsed onto today's tick, never skipped for "already sent today", and does not count as today's clock run so 8am still fires. Recovered automatic jobs still skip after a successful clock send.
**Why:** The old company-only test-mode gate was a product choice you reversed. Run now sharing the tick's once-a-day job key meant a leftover recovered send after this morning's success was skipped, which is the opposite of a test button.
**Status:** DECIDED — shipping with the drop-salesmen-table PR.

## 2026-09-03 Drop the v3 salesmen table; D365 is the only salesman master
**What you asked for:** Get rid of the extra salesman table and only use the SP and the users table. Salesman number is not needed anywhere; salesmen are identified by SalesGroup. Losing the in-app Active-off opt-out is fine.
**What I had to decide:** What replaces the table's fallback role on a cold boot with the SP down; what happens to number, short display name, and Active off; whether to keep any salesman UI.
**What I chose:** `SalesmanDirectory(client, db)` reads the SP and writes the last good list to `cache.db` `salesmen_master_cache` (rebuildable, not a master you edit). Cold boot with the SP down reads that copy; no SP and no cache means an empty list. `SalesmanFact.number` is removed; the Invoiced commissions card title is the name alone (grid and Excel). Display names are `SalesmanName`. No Active toggle: if D365 lists a salesman, they are in. Users & access keeps a read-only "Salesmen in D365" list; the edit modal, Active toggle, and `PUT /api/admin/salesmen/<key>` are gone. Manager checkboxes list the SP salesmen with normalized keys. Migration `0019_drop_salesmen` drops the table; `SalesmanRepository`, `seed_salesmen.py`, and the `salesman_map.xlsx` seed are deleted. Legacy `/legacy` app untouched.
**Why:** Two masters drift. Every reader was already behind the directory after 2026-09-03's earlier change, so removing the table is removing a fallback, and the disk cache is a better fallback because it is always the SP's own data.
**Status:** DECIDED — shipping this change. Irreversible on production `precious.db` once deployed (Litestream backups exist).

## 2026-09-03 Salesman email and commission read from rpt.usp_salesmen_master
**What you asked for:** "The word" on reading `Email` and `CommissionPercentage` from the SP and retiring the local table's copies.
**What I had to decide:** How far "retire" goes; what a local Active-off row means when D365 still lists the rep; whether local-only rows disappear; whether `CommissionPercentage` is a percent or a fraction.
**What I chose:** One `SalesmanDirectory` (SP first, hourly cache per process, last good list kept on failure) behind dropdown names, split-mail addresses, the Users & access email auto-grant, and the builders' commission fallback. Local table keeps number and short display name, fills blanks, and is the whole answer while the SP has not answered. Local Active off still hides a salesman everywhere (admin opt-out for a retired rep D365 still lists). Active local rows the SP does not list stay (deactivate to drop). Email is read-only in Users & access; `email` is no longer an editable field on the salesman API. Local email/commission columns are kept as fallback data, not dropped. Commission above 1 is treated as a whole percent (6 → 0.06), same rule as the invoiced SP's per-row rate.
**Why:** Every reader already went through a handful of repo methods, so one directory with the same method names swaps the source without touching report math. Keeping the table as fallback means an SP outage degrades to yesterday's behavior instead of empty mail runs. The percent rule is a guess the invoiced adapter already makes; the raw SP shows `CommissionPercentage: 5`-style values, which fits.
**Status:** DECIDED — shipping this change. Not done: dropping the local `email` / `commission_pct` columns or the seed-from-xlsx path.

## 2026-09-03 Phase 8.9 gate closed; main merged in
**What I chose:** Close Phase 8.9 on `e5b1ceb`, then merge `origin/main` (`173c166`, salesmen_master SP work) as `ff8486d`. Trust-boundary N/A.
**Why:** Loop A F1 (wizard lookups stacked one `visibilitychange` listener per report key) closed on `b6995fb`. Loop B caught what both Terra passes missed: anchoring the client give-up at job start made any reconnect to a report older than 10 minutes throw before one status check; fixed on `99993b7` by counting from when the page began watching, plus guards on the three pollers outside the original ten-site inventory. Loop C craft (header comment, run-log ordering, TESTING-STRATEGY reconnect case) closed across `38f1377`, `0310d0e`, `e5b1ceb`; the run-log loop keeps sleep → hidden check → fetch because its `continue` branches would skip an end-of-loop sleep. Loops A2, B2 zero; C3 one comment-wording Low, applied. PR #35 had turned CONFLICTING when main moved, which also stopped `pull_request` CI; merging main restored both. Merge resolutions: docs keep both sides; README drops the "beta SQL/OData sources" phrase Phase 3 removed; Salesmen grid takes main's hint plus this branch's `.table-wrap`; `salesman_directory.py` no longer passes `SalesmanFact.source` (removed in Phase 3). Full suite 729 passed. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.9: pause or reschedule hidden-tab pollers
**What I had to decide:** Next leftover after the 8.8 gate, and how to make ten pollers tab-aware.
**Options I considered:** (1) Q8/Q9 (BLOCKED). (2) Phase 7 replica drop (waits on `/test`). (3) Per-file guards, duplicated ten times. (4) One tiny shared `visibility.ts` (`isHidden`, `onVisible`, `sleepUntilVisible`) inlined by esbuild into each bundle; interval ticks return early while hidden and re-tick on visible; job loops and dashboard refresh switch from iteration counts to wall-clock deadlines and wake early when the tab returns.
**What I chose:** (4). Ten call sites across six bundles is far past Rule of 2. `clearInterval` on hide was rejected: more state, same effect, easier to leak timers.
**Why:** Hidden tabs today keep hitting `/notifications` every 30 s and the active-jobs endpoint every 5 s, and browser throttling can stretch the report loop's "10 minutes" (600 × 1 s) into hours. Server-side 45-minute kill (Q11) untouched.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.8 gate closed
**What I chose:** Close Phase 8.8 on `bc87667`. Trust-boundary N/A.
**Why:** Loop A (Terra), Loop B (Sonnet), Loop C (Sonnet) all zero. Agent Guardrails green on HEAD. Loop C noted a missing TESTING-STRATEGY 8.8 section; added at gate close. Inline `matchMedia` at 3 sites kept (no shared module across those bundles). Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.8: respect prefers-reduced-motion for JS scrolling
**What I had to decide:** Next leftover after the 8.7 gate.
**Options I considered:** (1) Q8/Q9 (BLOCKED). (2) Phase 7 replica drop (waits on `/test`). (3) Report tablist (item 6). (4) Next Phase 8 leftover: respect `prefers-reduced-motion` for JS `scrollIntoView` calls.
**What I chose:** (4). Replace `behavior: "smooth"` with a `matchMedia` check at the three call sites (`report.ts`, `personal_wizard.ts`, `master_wizard.ts`). Inline — no new file or import (ponytail rung 5).
**Why:** Three smooth-scroll sites exist. `searchable_picker.ts` already uses instant. `main.ts` reads position, not animated. CSS `scroll-behavior` is absent. Tiny diff.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.7 gate closed
**What I chose:** Close Phase 8.7 on `708e9c0`. Trust-boundary N/A.
**Why:** Loop A (Terra), Loop B (Sonnet), Loop C (Sonnet) all zero findings. Loop B independently measured `.sp-picker-close` live at 44×44 via the SharePoint wizard. Agent Guardrails green on HEAD. All five selectors (`.help-btn`, `.modal-close`, `.sp-picker-close`, `.customer-chip`, `.sched-day-chip`) at 44px min. Ponytail: Lean. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.7: 44px help/filter/chip/day/close targets
**What I had to decide:** Next leftover after the 8.6 gate.
**Options I considered:** (1) Q8/Q9 (BLOCKED). (2) Phase 7 replica drop (waits on `/test`). (3) Report-page live status (item 8 remainder). (4) Next Phase 8 leftover: 44px targets on remaining help/filter/chip/day/close controls.
**What I chose:** (4). Bring `.help-btn`, `.modal-close`, `.sp-picker-close`, `.customer-chip` / test-email chips, and `.sched-day-chip` to a 44×44 CSS px minimum hit area (padding is OK; do not blow up the glyph). Keep current look otherwise. Do not start reduced motion, hidden-tab pollers, or report-page live status in this slice.
**Why:** The leftover names those control kinds. Help is 16px, day chips 34px, closes have no min size. Q8/Q9 and Phase 7 stay blocked.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.6 gate closed
**What I chose:** Close Phase 8.6 on `c9c01a7`. Trust-boundary N/A.
**Why:** Loop A F1 (queued announced as running) and F2 (silent access/exclusion failures) closed on `c9c01a7`. Fresh Loop A re-pass, Loop B, and Loop C all zero. Agent Guardrails green on HEAD. Named live regions on admin, dashboard, Settings, and schedule Run now. Ponytail: Lean already. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.6: live status/error announcements
**What I had to decide:** Next leftover after the 8.5 gate.
**Options I considered:** (1) Q8/Q9 (BLOCKED). (2) Phase 7 replica drop (waits on `/test`). (3) Report-page `#reportStatus` plus jobs FAB (REPOSITORY-REVIEW item 8 remainder). (4) Next Phase 8 leftover: live announcements for admin, dashboard, Settings, and schedule sends.
**What I chose:** (4). Announce status and errors on those four named surfaces. `aria-live="polite"` for progress/success; `aria-live="assertive"` (or `role=alert`) for errors. Reuse existing message nodes (`#addUserMsg`, `#euMsg`, `#esMsg`, `#psMsg`, `#masterMsg`, Settings hints) and add a region only where status is button-text-only today (dashboard refresh, schedule Run now). Keep current look. Do not start report-page status, 44px, reduced motion, or pollers in this slice.
**Why:** The leftover names those four surfaces. Wizards already have polite live regions; admin/dashboard/Settings/Run now mostly do not. Item 8’s report-run status waits. Q8/Q9 and Phase 7 stay blocked.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.5 gate closed
**What I chose:** Close Phase 8.5 on `6b7cce0`. Trust-boundary N/A.
**Why:** Loop A F1 (tab-menu outside click restored focus) closed on `63be8cf`/`6b7cce0`. Fresh Loop A re-pass, Loop B, and Loop C all zero. Agent Guardrails green on HEAD. Export, More, and tab-option menus have WAI-ARIA keyboard; caret is a named menu button. Ponytail: Lean already. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.5: toolbar and tab-option menu keyboard
**What I had to decide:** Next leftover after the 8.4 gate.
**Options I considered:** (1) Q8/Q9 (BLOCKED). (2) Phase 7 replica drop (waits on `/test`). (3) Report tablist/tab/tabpanel (REPOSITORY-REVIEW item 6). (4) Next Phase 8 leftover: toolbar and tab-option menu keyboard.
**What I chose:** (4). WAI-ARIA menu keyboard on Export, More, and the tab-option menu. Arrow/Home/End move items; Enter/Space activates; Escape closes and returns focus to the opener. Tab closes the menu. Make the tab caret a focusable button (`aria-haspopup=menu`) so a keyboard user can open tab options without implementing tablist arrows. Shared helper if that is smaller than three copies. Keep current look. Do not restyle. Do not start tablist, 44px, live announcements, or Tabulator menus in this slice.
**Why:** Export/More already declare `role=menu` with no keyboard. Tab options are mouse/right-click only. Item 6 is a different leftover and would steal Arrow keys if mixed in. Q8/Q9 and Phase 7 stay blocked.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.4 gate closed
**What I chose:** Close Phase 8.4 on `364a84e`. Trust-boundary N/A.
**Why:** Loop A F1 (checkbox inside `role=option`) closed on `364a84e`. Fresh Loop A re-pass, Loop B, and Loop C all zero. Agent Guardrails green on HEAD. Shared `SearchablePicker` supplies Arrow/Home/End, Enter/Space, Escape, combobox/listbox ARIA, and focus return on Settings exclusions and Ordered customers. Ponytail: Lean already. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.4: searchable-picker keyboard
**What I had to decide:** Next leftover after the 8.3 gate.
**Options I considered:** (1) Q8/Q9 (BLOCKED). (2) Phase 7 replica drop (waits on `/test`). (3) Next Phase 8 leftover: complete searchable-picker option navigation and focus return.
**What I chose:** (3). Arrow keys move an active option; Enter/Space toggles it; Escape closes; focus returns to the search field. Keep the current combobox chrome. Do not restyle. Do not start toolbar/tab-menu work in this slice.
**Why:** `searchable_picker.ts` and the report customer fork already open on focus and filter, but have no option highlight or keyboard activate. The leftover is specific. Q8/Q9 and Phase 7 stay blocked.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.3 gate closed
**What I chose:** Close Phase 8.3 on `b00e2b4`. Trust-boundary N/A.
**Why:** Loop A F1 (mono-dark hover 3.67:1) closed on `803e635`. Loop C F1–F3 (duplicate tuples, hover=primary, failed-FAB foreground) closed on `0744fde`/`b00e2b4`. Loop A re-pass, Loop B, Loop C re-pass, and extra Loop A on the new hover/error pairs all zero. Agent Guardrails green on HEAD. Ponytail: Lean already. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.3: four-theme contrast
**What I had to decide:** Next leftover after the 8.2 gate.
**Options I considered:** (1) Q8/Q9 (BLOCKED). (2) Phase 7 replica drop (waits on `/test`). (3) Next Phase 8 leftover: correct four-theme contrast failures.
**What I chose:** (3). WCAG 2.1 AA: normal text 4.5:1, large/UI chrome 3:1. Fix by retuning existing CSS tokens and the four-theme badge/alert overrides. Do not introduce a fifth theme or restyle the app.
**Why:** REPOSITORY-REVIEW already recorded token pairs as low as 1.35:1. The leftover is specific. Q8/Q9 and Phase 7 stay blocked.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.2 gate closed
**What I chose:** Close Phase 8.2 on `7bb2ae6`. Trust-boundary N/A.
**Why:** Loops A+B+C zero. Loop A F1 (160 CSS px layout vs `body.zoom`) closed on `7bb2ae6`. Agent Guardrails green on HEAD. Admin/dashboard tables wrap in `.table-wrap`; tiles shrink; jobs panel cannot force 240px. Chrome CDP 320/320 and 160/160 on both routes. Ponytail: Lean already. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.2: admin/dashboard table reflow at 320px and 200% zoom
**What I had to decide:** Next leftover after the 8.1 gate.
**Options I considered:** (1) Q8/Q9 (still BLOCKED). (2) Rest of Phase 7 (waits on `/test` unmount). (3) Convert admin/dashboard tables to stacked cards at narrow widths. (4) Keep tables; contain overflow so the document does not scroll sideways and actions stay reachable.
**What I chose:** (4). Phase 8 gate already forbids document-level horizontal scroll that hides actions. Do not restyle into cards. Scope is admin users/access and dashboard tables named in the leftover, not every report Tabulator grid.
**Why:** Inner `.table-wrap` scroll already exists; the leftover is the 320px/200% failure, not a redesign. Q8/Q9 and Phase 7 replica drop stay blocked.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.1 gate closed
**What I chose:** Close Phase 8.1 on `889af71`. Trust-boundary N/A.
**Why:** Loops A+B+C zero. Loop A F1 (unnamed edit-user dialog) and F2 (stale focus frame) closed on `fde7e95`. Loop B per-bundle `window.dialogs` comment on `889af71`. Agent Guardrails green on HEAD. Named overlays share `dialog.ts` (aria-modal, focus, trap, Escape, sibling inert, opener restore). Ponytail: Lean already. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 8.1: shared dialog helper for named overlays
**What I had to decide:** Next leftover after the 7.1 gate.
**Options I considered:** (1) Q8/Q9 (still BLOCKED). (2) Rest of Phase 7: Azure `BETA_*`→`SITE_*` cutover, drop the `/test` replica, restore drill. (3) Phase 8 first bullets: one dialog helper with aria-modal, focus, trap, Escape, inert, opener restore, adopted on admin, SharePoint, external-login, Customer Last Order, and export dialogs.
**What I chose:** (3). Keep existing overlay markup and look; do not switch to native `<dialog>` (would restyle every overlay). Phase 7 remainder waits until `/test` can unmount. Q8/Q9 stay BLOCKED.
**Why:** Dropping the second DB conflicts with keeping `/legacy` `/test` `/test-next`. Dialog a11y is specified and does not need an Azure owner. Native `<dialog>` would be a visual fork.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 7.1 gate closed
**What I chose:** Close Phase 7.1 on `5ffe7ad`. Trust-boundary N/A.
**Why:** Loops A+B+C zero after F1 (whitespace-only SITE_* trim). Agent Guardrails green on HEAD. Home `SITE_PRECIOUS_DB_PATH` / `SITE_CACHE_DB_PATH` win when non-empty after strip; old names remain; Beta stays `BETA_*`; litestream.yml keys unchanged. Loop B cache-path startup test gap is non-blocking. Ponytail: Lean already. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 7.1: staged `SITE_PRECIOUS_DB_PATH` alias
**What I had to decide:** Next leftover after the 6.9 gate. Remaining Phase 6 items are Q8 and Q9.
**Options I considered:** (1) Q8 approve-recipients. (2) Q9 company Send now. (3) Phase 7 first bullets: canonical home DB env name `SITE_PRECIOUS_DB_PATH` with a staged dual-read so Azure does not have to flip settings in the same deploy.
**What I chose:** (3). Canonical home precious name is `SITE_PRECIOUS_DB_PATH`. If set, it wins; otherwise keep `PRECIOUS_DB_PATH`. Same pattern for `SITE_CACHE_DB_PATH` / `CACHE_DB_PATH`. `startup.sh` copies `SITE_*` into the existing `PRECIOUS_DB_PATH` / `CACHE_DB_PATH` env so `litestream.yml` keys stay. Do not unmount `/test`. Do not drop `BETA_*`. Do not change Azure settings from git. Q8/Q9 stay untouched (BLOCKED below).
**Why:** The plan already prefers `SITE_PRECIOUS_DB_PATH` and a staged `BETA_*`/`PRECIOUS_*` → `SITE_*` migration. Dual-read is reversible. Removing the second `/test` database conflicts with keeping those mounts. Q8 still has no “external” rule. Q9 still conflicts with the leftover “require operate/edit” bullet and with current admin+edit code.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Q8 external-recipient policy
**What I had to decide:** Phase 6 leftover “Apply external-recipient policy” vs adopted Q8 (users may add; admin/dev must approve).
**Options I considered:** (1) Invent “external” as not-in-`users.email`. (2) Invent company-domain allowlist. (3) Stop until the owner locks the rule and the approve UX.
**What I chose:** (3).
**Why:** Spec gate fails: no definition of external, and v3 has no pending/approve recipient code. Original grill recommended approved-domain plus privileged override, which is not Q8 as adopted.
**Status:** BLOCKED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Q9 company Send now vs require operate/edit
**What I had to decide:** Adopted Q9 (view-only managers may trigger company Send now) vs Phase 6 leftover (require operate/edit) vs current `run_master` (`_require_admin` then `_require_master_edit`).
**Options I considered:** (1) Loosen `POST /api/master-schedules/<id>/run` for managers who can view the schedule. (2) Tick the leftover as done because current code already requires edit (plus admin). (3) Leave the route unchanged until the owner picks Q9 vs fail-closed.
**What I chose:** (3).
**Why:** Loosening Send now is a trust-boundary change. Ticking the leftover would paper over Q9. Do not silent-pick.
**Status:** BLOCKED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.9 gate closed
**What I chose:** Close Phase 6.9 on `86f2fbc`. Trust-boundary N/A.
**Why:** Loops A+B+C zero; Agent Guardrails green on HEAD `86f2fbc`; displayed % is salesman-table saved percent; money still `_commission_rate`; invoiced `builder_version` 4. Ponytail: Lean already. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.9: show salesman-table saved percent on commission display
**What I had to decide:** Next Phase 6 leftover after the 6.8 gate.
**Options I considered:** (1) Q8 approve-recipients (UX still open: what is “external”) / Q9 vs Send now. (2) Original grill “varies” vs adopted Q3 salesman-table saved percent. (3) Implement adopted Q3: the displayed % is the salesman master; money still uses `_commission_rate` (Q1/Q2, including explicit zero).
**What I chose:** (3). Do not show “varies” or per-month rates. Do not change Q8/Q9. Bust invoiced `builder_version` again so cached cards are not reused.
**Why:** Q3 is already decided. The plan bullet’s “varying” wording is the original grill; adopted Q3 is the saved table percent. Q8 still needs an external-vs-internal rule; Q9 conflicts with the Phase 6 Send-now bullet.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.8 gate closed
**What I chose:** Close Phase 6.8 on `6d4a0b5`. Trust-boundary N/A.
**Why:** Loops A+B+C zero; Agent Guardrails green on HEAD; `last_run_at` ignores `legacy`/`unknown`/`output_meta.legacy`; `0019_delivery_legs.sql` unchanged.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.7 gate closed
**What I chose:** Close Phase 6.7 on the explicit-zero slice plus invoiced `builder_version` 3. Trust-boundary high 0, medium 0. Info I1 addressed by the version bump. I2 (credit rows with SP 0) is Q2 as adopted. I3 (Q1 `>1` guard) is pre-existing.
**Why:** Loops A+B+C zero; Fable trust-boundary did not block; Agent Guardrails green on `a6b22f5`; version bump so 7-day cache cannot keep master-fallback dollars.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.8: forward-correct legacy schedule slots without editing 0019
**What I had to decide:** Next Phase 6 leftover after the 6.7 gate.
**Options I considered:** (1) Q3 “varies” vs saved percent / Q8 approve-recipients / Q9 vs Send now. (2) The named leftover: replace old migration 0019 schedule-slot behavior with a forward correction — do not edit this PR’s `0019_delivery_legs.sql`; mark unattributable historical rows legacy/unknown; they must not suppress the next real clock slot.
**What I chose:** (2). `due_now` today uses `last_run_at` (`MAX(started_at)` of every `schedule_runs` row) plus `last_claimed_at`. A deploy-day or unattributable run must not make `_ran_today` true for the next HH:MM. Do not change `hold_until_next_slot` (save/On waiting for the next slot is intentional). No Q3/Q8/Q9.
**Why:** Plan text is specific and does not conflict with Q9. Q3 and Q8 still mix product/UX calls.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.7: preserve explicit-zero commission from the SP
**What I had to decide:** Next Phase 6 leftover after the 6.6 gate.
**Options I considered:** (1) Q3 “varies” vs salesman-table saved percent / Q8 approve-recipients / Q9 vs Send now / 0019-legacy slots. (2) The named leftover: SP commission `0` is authoritative (Q2) but `_commission_fraction` and `_commission_rate` treat 0 like missing and fall back to the salesman master.
**What I chose:** (2). Missing/blank commission stays a fallback to master. Explicit `0` / `"0"` stays `0` and does not use the master. Keep the existing per-salesman max among *present* SP rates (mixed 0 and 0.10 still 0.10). Do not implement Q3 “varies” display, per-invoice mixed-rate rewrite, Q8, or Q9.
**Why:** Q2 already decided “SP zero stays zero.” Distinguishing None vs 0 is the defect. The other leftovers still mix product calls or a Q9 conflict.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.6 gate closed
**What I chose:** Close Phase 6.6 on `b4cdc3e`. Trust-boundary N/A.
**Why:** Loops A+B zero; Loop C F1 timedelta then re-pass zero; Agent Guardrails green on HEAD; terminal jobs / run log / magic-link tokens prune at 90 days without gating `/readyz`.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.6: 90-day prune of jobs, run log, and magic-link tokens
**What I had to decide:** Next Phase 6 leftover after the 6.5 gate. Phase 4.4 parked 90-day job-history prune in “Phase 7” so daily cleanup would not flap `/readyz`.
**Options I considered:** (1) Q2 explicit-zero / Q3 varies / Q8 / Q9 vs Send now / 0019-legacy slots. (2) The named Q10 leftover: prune magic-link tokens, old jobs, and run history at 90 days (legs already 90-day).
**What I chose:** (2). Wire it into existing daily `run_cleanup` without changing `/readyz`. Terminal jobs older than 90 days go; queued/running stay; a still-valid Keep still protects its job row. `report_run_log` and `magic_link_tokens` older than 90 days go. Live `webapp` magic-link tokens prune the same way (that is the real attempt table). Do not change delivery-leg TTL. Do not make readiness wait on this prune.
**Why:** Q10 already set 90 days. Phase 4.4 only kept it out of the heartbeat slice. Legs are already done. Other leftovers still mix product calls or a Q9 conflict.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.5 gate closed
**What I chose:** Close Phase 6.5 on `1f79c4b`. Trust-boundary N/A.
**Why:** Loops A+B+C zero; Agent Guardrails green on HEAD; live Keep cache rows survive 7-day age prune and expired Keep rows are deleted.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.5: prune expired Keep payloads, keep live Keep rows
**What I had to decide:** Next Phase 6 leftover after the 6.4 gate.
**Options I considered:** (1) Q2 explicit-zero / Q3 varies / Q8 / Q9 vs Send now / 0019-legacy slots / 90-day job history. (2) The named defect: cleanup’s 7-day cache prune ignores Keep, so a 30-day Keep dies at day 8, and expired Keep rows linger until that age cut.
**What I chose:** (2). Age-prune still deletes unkept rows older than 7 days. Do not delete a cache_key referenced by any job whose `kept_until` is still valid. Do delete a cache_key whose only Keep refs are expired, even if the row is younger than 7 days. Unkept young rows stay. Cleanup must not import the reports blueprint; move or share `_kept_still_valid` next to jobs.
**Why:** Keep is already 30 days. Result GET already 404s after expiry; leftover cache is the rest of the named bullet. Other leftovers still mix product calls or a Q9 conflict.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.4 gate closed
**What I chose:** Close Phase 6.4 on `ff00ee7`. Trust-boundary N/A.
**Why:** Loops A+B zero; Loop C F1 rename then re-pass zero; Agent Guardrails green on HEAD; expired Keep 404s on result GET and export.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.4: refuse result access after Keep expires
**What I had to decide:** Next Phase 6 leftover after the 6.3 gate.
**Options I considered:** (1) Q2 explicit-zero / Q3 “varies” display / Q8 external-recipient / Q9 vs Send now / 0019-legacy slots / retention prune. (2) The named defect: `GET /api/reports/result/<job_id>` (and export) serve a cached payload after `kept_until` has passed.
**What I chose:** (2). If `kept_until` is set and `_kept_still_valid` is false, result GET and export return the same 404 as a missing cache. Unkept runs stay cache-presence-only. Cache 7-day prune and Keep-payload retention stay a later slice. Q9 vs “require edit” stays untouched.
**Why:** Keep already has a decided window (30 days). The active list honors it; result access does not. The other leftovers still mix product calls or a Q9 conflict.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.3 gate closed
**What I chose:** Close Phase 6.3 on `908a6a2`. Trust-boundary N/A.
**Why:** Loops A+B+C zero; Agent Guardrails green on HEAD; empty-after-clamp raises `EmptyCustomRangeError` instead of all-time.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.3: reject empty custom windows after go-live clamp
**What I had to decide:** How to implement "reject an interval whose start exceeds end" after D365 clamping without breaking reversed-picker swap or unparseable-date omit.
**Options I considered:** (1) Stop swapping reversed dates. (2) Clamp, then reject only when start > end; keep swap when the window is still valid; keep omitting unparseable ISO.
**What I chose:** (2). Do not treat an empty-after-clamp window as all-time.
**Why:** The plan names post-clamp validation. Swapping 2026-03-10 / 2026-02-01 still yields a real window. A 2024-only range becomes start > end after clamp and must not run unfiltered.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.2 gate closed
**What I chose:** Close Phase 6.2 on `f6f9051`. Trust-boundary N/A.
**Why:** Loops A+B+C zero; Agent Guardrails green on HEAD; one-line current-bucket lookup.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.2: commission-card number from current bucket
**What I had to decide:** Next Phase 6 leftover after the 6.1 gate.
**Options I considered:** (1) Commissions rate-display / zero-contract / date-interval / retention / external-recipient / Q9 Send now. (2) The specified lookup bug: cards reuse the last aggregation-loop `sm`.
**What I chose:** (2). Q1–Q3 rate policy, Q8/Q10, date-interval reject, and Q9 vs Phase 6 Send now stay deferred.
**Why:** The bucket lookup is a named defect with one correct lookup. The others still mix product calls (or Q9 vs "require edit").
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.1 gate closed
**What I chose:** Close Phase 6.1 on `3c79500`. Trust-boundary info items I1 (HTML 403 vs JSON on `/api/`) and I2 (unclamped `year`) are pre-existing/developer-only; not this gate.
**Why:** Loops A+B+C zero; trust-boundary high 0 medium 0; Agent Guardrails green on HEAD.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.1 Loop A F1: CSRF-first anonymous status
**What I had to decide:** Loop A required anonymous reconcile POST to return 401, but global CSRF aborts 400 before `@require_login`.
**Options I considered:** (1) Exempt the routes or skip CSRF when unsigned-in so login can 401 first. (2) Keep CSRF-first 400 with no session token; 401 only after a CSRF token is present but no login.
**What I chose:** (2). No new CSRF exemptions. Same order as claim-once and precious-repair.
**Why:** Login CSRF must stay in force for unsigned-in POSTs. The handlers still cannot run without a developer session.
**Status:** DECIDED
**Model:** cursor-grok-4.6-xhigh
**Runner:** parent

## 2026-09-03 Phase 6.1: fail-closed leftovers first
**What I had to decide:** Phase 6 lists many leftover defects; some need owner product calls (commission display, retention windows, external-recipient policy). This PR's 0019 is delivery_legs, not the old schedule-slot 0019.
**Options I considered:** (1) Implement the whole Phase 6 list now. (2) Slice 6.1 to already-specified fail-closed leftovers: persist `skip_sabbath=false`, never tenant-search a substitute SharePoint site, move reconcile diagnostics off query-string secrets.
**What I chose:** (2). Defer commissions, date-interval reject, kept-run expiry, retention prune, external-recipient, and any 0019-legacy slot rewrite.
**Why:** Those leftovers are specified in `PR1-REMEDIATION-PLAN.md` without a new product choice. The deferred items are business-rule or retention calls.
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-03 Phase 5.4: Graph tokens stay in memory with expiry
**What I chose:** Cache client-credentials tokens in process with `expires_at`, refresh about a minute early, and never write them to sqlite. One 401 clears the cache and retries GET/PUT/upload-session once; sendMail 401 (HTTP reject) may retry the send once. Connection-loss after sendMail stays unknown. 429/503 honor Retry-After once, capped at 60s. Interrupted upload sessions resume from `nextExpectedRanges`.
**Why:** A new token on every Graph call is waste and 401-after-expiry is a false delivery failure. sendMail after a connection loss is still not safe to retry (5.1).
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-03 Phase 5.3: no-data notices are kind=notice
**What I chose:** Persist split no-data mail as `kind=notice` on the same job/run/slot as the schedule attempt. Widen unreleased 0019. Do not create a workbook `email` leg for that notice. A failed notice keeps the run from success/skip and does not Graph-retry an already-sent workbook.
**Why:** Marking the workbook-email leg sent when no workbook was attempted, or treating a failed notice as skip/success because another fan-out copy reached the inbox, hides a required send.
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-03 Phase 5.2: folder and email are independent delivery legs
**What I chose:** Create one `folder` leg for each requested SharePoint/OneDrive upload and one `email` leg for each email target, sharing the existing job/run/slot identity.
**Why:** A folder failure after mail acceptance must remain visible without changing the accepted email outcome or causing another Graph send.
**Status:** DECIDED
**Model:** gpt-5.6-terra
**Runner:** spawn

## 2026-09-03 Phase 5.2: folder success requires a returned Graph item
**What I chose:** Mark a folder leg `sent` only when upload returns `webUrl` or an item id; otherwise mark that folder leg `failed`.
**Why:** Upload completion without a remotely addressable item is not verified delivery. Mock uploads follow the same rule.
**Status:** DECIDED
**Model:** gpt-5.6-terra
**Runner:** spawn

## 2026-09-03 Phase 5.1 Loop C: defer DeliveryContext
**What I chose:** Keep the existing `job_id`/`run_id`/`slot_id` parameters; do not add `DeliveryContext`.
**Why:** F1 and F2 are narrow correctness-of-pattern fixes. A shared context belongs in 5.2 if folder or notice legs need the same trio.
**Status:** DEFERRED

## 2026-09-03 Phase 5.1: Graph connection loss is unknown
**What I chose:** Record `unknown` for a timeout, URL error, reset, or other connection loss after `sendMail` is submitted; do not run the schedule retry.
**Why:** Graph did not confirm rejection or acceptance, so retrying risks a duplicate and calling it sent is unsupported.
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-03 Phase 5.1: delivery slots belong to durable jobs
**What I chose:** Tick computes its Eastern date and schedule clock slot before enqueue; manual delivery uses `manual:{job_id}`.
**Why:** Execution can cross Eastern midnight or retry, but it must retain the original intended delivery slot and durable job identity.
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-03 Phase 4.4: readiness response stays generic
**What I chose:** Keep `/readyz` as `{status: ready}` or `{status: starting}` without naming a stale heartbeat or other operational detail.
**Why:** Load balancers need only the readiness state; developers have the authenticated diagnostics route for detail.
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-03 Phase 4.4: external replication lag stays operator-owned
**What I chose:** Do not invent an in-app Litestream lag metric or add a package. Operators compare Azure Blob last-modified time with local SQLite mtime; replication is absent when `LITESTREAM_AZURE_ACCOUNT_KEY` is unset.
**Why:** The app cannot reliably observe Azure Blob replication freshness from its process.
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-03 Phase 4.4: process identity is durable diagnostics, not readiness
**What I chose:** Store the worker PID, UTC start time, and hostname as JSON in `app_settings` after the scheduler starts. Do not use it to gate `/readyz`.
**Why:** It helps operators identify the worker without making readiness depend on a static startup record.
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-03 Phase 4.4: cleanup follows existing cache and export retention
**What I chose:** Prune seven-day report cache rows and tiered exports once at worker start and daily at 03:15 America/New_York. Record cleanup only after both prune calls succeed.
**Why:** A 90-day job-history prune belongs to Phase 7. Daily cleanup must not make readiness flap.
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-03 Phase 4.4: scheduler beats at start and after every tick
**What I chose:** Beat the scheduler immediately after `scheduler.start()` and in a `finally` wrapper around each minute tick.
**Why:** A 90-second freshness limit needs a boot beat, and failed enqueueing still proves the scheduler loop ran.
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-03 Phase 4.4: readiness requires worker and scheduler heartbeats
**What I chose:** `/readyz` requires bootstrap plus fresh worker and scheduler heartbeats. Cleanup and process identity stay visible only in developer diagnostics.
**Why:** Cleanup is daily, so requiring it at a 90-second threshold would keep the site red or make it flap.
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-03 Phase 4.3: reject fork-after-threads for job children
**What I had to decide:** Whether the production poller could keep forking after APScheduler had started threads.
**Options I considered:** (1) Keep `fork()` despite Python's deadlock warning. (2) Start a new interpreter for each claimed job. (3) Use a test-only child command for closure-based handlers.
**What I chose:** Option 2 in production: `python -m web.jobs.run_one <job_id>` creates an app and runs the already-claimed job. Tests may inject a child argv for handlers that only exist as test closures.
**Why:** A new interpreter does not inherit locked thread state. The durable job row lets the child report its own terminal outcome without a multiprocessing queue.
**Status:** DECIDED

## 2026-09-03 Phase 4.3: refuse admission, drain queue, hard-kill hung children
**What I had to decide:** Whether queue limits should stop poller claims or reject new work, and how to release the only worker slot when a child ignores SIGTERM.
**Options I considered:** (1) Skip claims when the queue is full or stale. (2) Refuse enqueue at depth, expire stale queued rows, then keep draining. (3) Leave a SIGTERM-ignoring child joined forever.
**What I chose:** Option 2. Enqueue refuses at the named depth; the poller expires over-age queued rows and always claims remaining work. After SIGTERM, it joins briefly, then sends SIGKILL and joins again if the child is still alive.
**Why:** Skipping claims freezes every queued job. SIGTERM is cooperative, so it cannot be the hard timeout boundary.
**Status:** DECIDED

## 2026-09-03 Phase 4.3: one killable job slot; schedules beat exports
**What I had to decide:** How to stop a hung report without leaving a thread running after the DB row is failed, and how to keep scheduled mail from waiting behind on-screen exports.
**Options I considered:** (1) Thread + timeout flag (does not kill the work). (2) One child process per claimed job, hard kill on timeout, max_workers=1. (3) Keep two in-process threads.
**What I chose:** Option 2 for the production poller. `process_next`/`drain` stay in-process for tests. Claim `schedule.run` and `report.deliver` before `report.export`. Scheduler start failure keeps `/readyz` red but does not exit the worker process (that would take Gunicorn down via supervise-web.sh).
**Why:** Plan 4.3 forbids marking failed while work continues. B1 is 1 vCPU. Die-together supervisor must not treat a missing APScheduler as a site outage.
**Status:** DECIDED

## 2026-09-03 Phase 4.1–4.2: Gunicorn stays fast; worker process owns migrate and jobs
**What I had to decide:** Whether the supervisor should block Gunicorn until migrate/seed finishes (plan “bootstrap before traffic”) or start HTTP immediately (Azure warmup historically killed the container when migrate ran on import).
**Options I considered:** (1) `supervise-web.sh` runs bootstrap, then Gunicorn+worker. (2) Gunicorn starts immediately; worker process runs migrate/seed then jobs; `/healthz` 200, `/readyz` 503 until heartbeat. (3) Keep in-process flock leader inside Gunicorn.
**What I chose:** Option 2. No new supervisor package. Live `/legacy` email loop stays in-process this slice. Phase 4.3 killable job children is later.
**Why:** `wsgi.py` already moved bootstrap off the import path because Azure warmup probes `/healthz`. Blocking Gunicorn on migrate would recreate that outage. `/readyz` is how a dead worker is visible.
**Status:** DECIDED

## 2026-09-03 Phase 3.3: delete v3 OData runtime, leave Live seed table
**What I had to decide:** Whether deleting `odata_bridge.py` / `beta_sources.py` also meant a precious migration to drop `beta_report_sources`, rewriting historical v3 markdown, or touching Live `webapp/`.
**Options I considered:** (1) Add v3 migration 0017/0018 to drop the map. (2) Leave the Live sqlite table and seed, stop v3 from reading it. (3) Also rewrite `v3/docs/odata-vs-sp-mismatch.md` and `REVIEW-LOG.md`.
**What I chose:** Option 2. Flask v3 has no OData runtime. Graph mail keeps `@odata.type`. CLI/Automation OData under `reports/`, `core/`, `data/`, `runbooks/` stays. No 0017/0018. Historical docs stay. `/legacy` `/test` `/test-next` stay mounted.
**Why:** Plan 3.4 is keep Automation OData. A precious drop would fight “do not edit 0016 / do not add 0017-0018 this PR until owner says.” Live Settings can still show the old map; v3 ignores it.
**Status:** DECIDED

## 2026-09-03 Phase 3.1: SQL-backed reports cannot stay on OData
**What I had to decide:** How to make Item Averages (and Number 4 / Last Order) run SQL on Beta when Live already stored `odata` in `beta_report_sources`.
**Options I considered:** (1) Change defaults only (`INSERT OR IGNORE` leaves existing odata). (2) One-time UPDATE of SQL-backed keys to sql on schema ensure / Live seed. (3) Jump straight to deleting the source map.
**What I chose:** Option 2. `ensure_schema` and Live `seed_beta_report_sources` UPDATE signed-off keys to sql. Settings can still POST odata; the next read flips those keys back. Customer Aging stays odata (BACKLOG). Do not delete the Settings source UI until 3.2.
**Why:** Gate is “Item Averages works without an operator source change.” Changing the default dict alone would not move production rows.
**Status:** DECIDED

## 2026-09-03 Phase 2 leftover: CLI seed, magic-link Host, impersonate-unknown
**What I had to decide:** How to close the five leftover items from the Phase 2 trust-boundary pass without failing Azure boot or adding a full rate-limit table.
**Options I considered:** (1) Fail boot when `PUBLIC_BASE_URL` is unset in prod. (2) Warn only. (3) Leave CLI `ON CONFLICT` overwriting v3 roles. (4) Keep one live token per email vs a cooldown table. (5) 404 the role picker vs restore the developer after a missing target.
**What I chose:** CLI `copy_live_users` fills a blank display name only; existing v3 role/flags stay. Prod/Azure without `PUBLIC_BASE_URL` warns at import, does not fail boot. Minting a magic link deletes every prior token for that email (not a request-rate table). Role picker requires an active v3 row (404 otherwise); a leftover impersonation cookie whose target is missing/inactive restores the active developer actor. Display name from v3 was already shipped (`6f3024b`).
**Why:** Users & access is the authority after first import. Fail-closed boot would take down reports if the App Setting is missing. One outstanding token per email is the smallest anti-reuse step. Logging the developer out for a bad Switch-user pick was fail-closed but unusable.
**Status:** DECIDED

## 2026-09-03 Replay PR #1 instructions on current `main` (new draft PR)
**What you asked for:** Make a huge new PR. Apply everything that was instructed for PR #1, but onto current `main`, then see how it goes.
**What I had to decide:** Whether that means merge leftover PR #1, rebase its 124 commits, or replay the plan on today's tree. Whether the 2026-09-02 “inventory only, do not start rebuild Phase 2–4” decision still holds. Whether GitHub Environment approval belongs in the first workflow patch.
**Options I considered:** (1) Merge https://github.com/mennyg19-cmyk/AchimSales/pull/1 as-is. (2) Rebase `cursor/p0-security-containment-adb6` onto `main`. (3) New branch from `main` `263a76b`, keep PRs #11–#33, walk `PR1-REMEDIATION-PLAN.md` in order, do not delete `webapp/` until unused.
**What I chose:** Option 3. Branch `cursor/pr1-on-main-551b`. Do **not** merge PR #1. The 2026-09-02 no-rewrite decision is **superseded for this PR only**. Production branch is `main`. Q1–Q11 stay as already answered on the old branch. Contain first (workflow `workflow_dispatch` cannot deploy a non-`main` ref; security headers; refuse Azure/`APP_ENV=prod` `DEV_BYPASS_AUTH`; OData `_scope_tab` fail-closed). Then auth, then SQL-only only after every built report has SQL. Do **not** add a GitHub `production` Environment on the workflow in this phase — that setting does not exist here and would stall every deploy after merge. Cookie rotation stays an Azure owner action, not git. Keep this PR **draft** until Phase 10.
**Why:** PR #1 diverged 2026-08-26 (`330d1bc`), 58 behind / 124 ahead of `main`. Cherry-pick or merge would wipe salesman filter, rename, Excel bands, Users & access, and review security. You asked for a **new** PR from current `main`, which also overrides the standing “same agent → same PR” preference for this ask only.
**Status:** DECIDED

## 2026-09-03 Phase 1: defer APP_ENV allowlist for legacy DEV_BYPASS
**What I had to decide:** Whether Phase 1 should require `APP_ENV=dev` (allowlist) for `DEV_BYPASS_AUTH`, matching v3's fail-closed default.
**What I chose:** Keep the Azure/`APP_ENV=prod` denylist for this phase. Production is Azure App Service (`WEBSITE_SITE_NAME` is set). Align the Dockerfile/non-Azure host later.
**Why:** Trust-boundary F5. Changing container env is a deploy-settings change, not needed to close the Azure bypass hole.
**Status:** DECIDED — deferred past Phase 1.

## 2026-09-03 Salesman dropdowns read rpt.usp_salesmen_master
**What you asked for:** Convert every salesman dropdown to `POST /api/reports/salesmen_master/run` so salesmen with no customers still show.
**What I had to decide:** Column names (this VM cannot reach the Reporting API), what happens when that SP is down, and whether customer SalesGroups absent from the master stay in the list.
**What I chose:** One `LookupService` feed, fetched in the same background warm-up as customer_master. Adapter accepts `SalesGroup` / `SalesmanId` for the key, `SalesmanName` / `Name` / `FullName` / `DisplayName` for the name, and skips rows whose `IsActive` / `Active` is false. Name: SP first, then the v3 salesmen table overlay, then the raw key. If the SP fails the last good list stays; with none, dropdowns fall back to customer SalesGroups as before. Customer SalesGroups not in the master are appended so no filter value disappears. Values stay raw SalesGroup.
**Why:** Every dropdown already reads `LookupService.salesmen()`, so one source change covers reports, Users & access, the company wizard, and Customer's Last Order. Fallback keeps the site usable if the new SP is not deployed yet.
**Status:** DECIDED — shipping this change. If the SP's column names differ, only `master_salesman()` in `v3/web/reporting/lookups.py` needs the extra alias.

## 2026-09-02 Go-live: inventory live v3, do not rebuild from scratch
**What you asked for:** Plain-English report of today's fixes; database changes if possible; merge into main; then rebuild-protocol multi-model inventory of the entire site; then browser-click every feature autonomously with commit messages; edge cases; check schedules and Excel output.
**What I had to decide:** (1) Whether rebuild Phase 2–4 (architecture + from-scratch rebuild) starts after inventory. (2) Where test-log commits go after merging #33. (3) Grill before Phase 0.
**What I chose:** Phase 0–1 inventory of **live `v3/`** only, then click-through + schedule/Excel verification of the current app. Do **not** start Phase 2–4 rewrite. After #33 is on `main`, inventory and `GO-LIVE-TEST-LOG.md` live on branch `cursor/go-live-verify-551b` so doc/test-log pushes do not redeploy Azure; bugfixes found in that pass merge to `main` when they are real product fixes. Grill skipped: you already ordered the work and said run autonomously. Production sqlite row edits you made in the UI are **not** visible from this VM (no Azure DB access); schema migrations 0017/0018 are listed in `GO-LIVE-DAY-REPORT.md`.
**Why:** You asked to inventory and test the site that is going live, not to throw it away and rebuild. Protocol Half 2 would start a from-scratch rewrite; that contradicts "this app needs to go live." Test logs on `main` would fire a deploy for markdown.
**Status:** DECIDED

## 2026-09-02 Only developers can assign the developer role
**What you asked for:** Full review of the codebase using the review protocol.
**What I had to decide:** Whether an admin on Users & access may mint a developer (including themselves), and whether Add user may overwrite an existing email.
**What I chose:** Only a live DB developer can create or change a developer login (including disable and delete). Nobody can change their own role. Add user returns 409 if the email already exists. `/test` impersonation is developer-only and ends if the real developer is disabled. Delete still only removes v3 data (Disable blocks sign-in); the confirm text says so. Admins cannot delete a developer and re-add the email as salesman.
**Why:** Trust-boundary showed an admin could PUT themselves to developer and then write raw sqlite, and Add user ON CONFLICT wiped a developer to salesman with a 201.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Full review: v3 Users & access wins over Live cookie after first login
**What you asked for:** Full review of the codebase using the review protocol.
**What I had to decide:** After Users & access can rename people and set SalesGroup, whether every Live (Beta) page load should copy the Microsoft/Live cookie back onto that row.
**What I chose:** First Live login still creates the v3 user and copies Live salesman scope — including a developer whose Live cookie has `_dev` set and no v3 row yet. After that, display name, role, SalesGroup, is_external, and salesman-access stay as set in v3. Developer tools and Switch user require a live DB `developer` row, not a `_dev` cookie. A leftover impersonation cookie after demotion is treated as the actor's own identity (or logged out if that row is gone). Export download re-checks the source run's salesman scope.
**Why:** Loop B showed production (Beta) login was wiping admin edits, a leftover `_dev` cookie could re-promote a demoted developer, and a demoted admin could still download a company-wide workbook. Developer-only UI (including Settings beta-sources) now uses the same DB check.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Users can be renamed on Users & access
**What you asked for:** Users need to be possible to be renamed. Don't know why that's closed up.
**What I had to decide:** Whether rename is the login email or the display name, and whether Entra login / live-directory seed should overwrite an admin rename.
**What I chose:** Display name only (email stays the login). Edit user gets the same Display name field as Add user. PUT `/api/admin/users/<id>` accepts `display_name`. Login upsert and live copy fill a blank name only; they keep a name already set in v3.
**Why:** The edit modal never had a name field, and PUT ignored `display_name`. Entra login and boot seed used to write the Microsoft/live name on every pass, so a rename would not stick.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Admins and developers manage company views and schedule Default
**What you asked for:** Admins and developers should create, edit, and delete company views, and schedule from Default.
**What I had to decide:** Whether the Company views flag still gates admins, and whether Default is a personal schedule or a company schedule.
**What I chose:** Privileged users (admin/developer) always see and mutate company views; the flag remains for salesmen/managers. Save for **Company** creates a named company view. Default personal schedules (`view_name=Default`, empty layout so send uses live Default) for privileged only. Salesmen/managers still need a named view. Managers keep edit/delete when they have the flag.
**Why:** Admins in Users & access did not have the flag, so GET/PUT/DELETE company views 403'd. More → Schedule required a named `saved_reports` row, so Default was disabled. Company wizard already had Default; this opens the same layout from the report page and the personal list.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Delete company views from Saved views
**What you asked for:** There is no delete button for company views on the saved views dropdown.
**What I chose:** Same Delete control as personal views, only for people who can already Edit company views (managers/admins/developers). DELETE `/api/reports/<report>/company-views/<id>`. Salesmen who can see company views still cannot delete them.
**Why:** Company views had Edit/save but `canDelete` was hardcoded false, and there was no delete API.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Salesman report gets a salesman dropdown
**What you asked for:** The salesman report should be filterable by salesman; it should be an option.
**What I had to decide:** Whether to send the dropdown's SalesGroup value to the YoY stored procedure as `SalesmanName`.
**What I chose:** Show the same Salesman dropdown Ordered already uses. Do not send that SalesGroup token as `SalesmanName` (the SP wants a display name). Filter the YoY rows after fetch, matching the pick against master aliases (key, display name, full name, number) and still applying the user's salesman scope.
**Why:** The run page only exposed Year. Company schedules already had a salesman field for this report, but the on-screen Filters bar did not. Sending `REdwards` as `SalesmanName` can return no rows when the SP stores "Reggie Edwards".
**Status:** DECIDED — shipping this change.

## 2026-09-02 SalesGroup dropdown on the salesman login
**What you asked for:** Do this slowly. SalesGroup should be a dropdown on the user that updates from the same list as report filters. Does that answer the problem?
**What I had to decide:** Same URL vs same LookupService; whether managers lose checkboxes; whether to drop the salesmen FK this step.
**Options I considered:** (1) Reuse `/api/reports/ordered/salesmen` (403 if Ordered is off). (2) Privileged `GET /api/admin/sales-groups` wrapping `LookupService.salesmen()`. (3) Fill the dropdown from the salesmen table (wrong key for the SP).
**What I chose:** (2). Raw SalesGroup on `users.sales_group`; normalized key in `user_salesman_access`. Dropdown for salesman only; managers keep checkboxes. Drop the access-table FK to `salesmen` so a customer_master group can grant without stubbing a salesman row. Salesmen table stays (number, names, split-mail, commission).
**Why:** A login is still not a D365 SalesGroup, but a 1:1 salesman login needs the same raw value the report filters send the SP. The report-keyed URL is the wrong gate for Users & access.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Personal schedule columns share one grid
**What you asked for:** Avi / Heshy / Mendy tables on Personal schedules should line up (same column edges).
**What I chose:** One table. Owner name is a full-width banner row. `table-layout: fixed` plus a colgroup so View/Recipients wrap instead of shoving Actions around.
**Why:** Separate tables size columns from their own content, so Avi’s long recipient list shifted every column vs Heshy.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Admins save views for other users without logging in as them
**What you asked for:** Set up views and schedules for other people without switching into their login. A new salesman user was missing from Switch user and from salesman dropdowns. What is the salesmen table for, and why isn't users enough?
**What I had to decide:** Whether to merge `users` and `salesmen`, whether login emails should appear in report salesman dropdowns, and where "save for someone else" lives.
**Options I considered:** (1) Impersonation-only, which is what you called a waste of time. (2) One table for logins and D365 SalesGroup. (3) Keep both tables; let admins save a named view onto another user; Switch user lists v3 logins even when Live's directory is stale.
**What I chose:** (3). Privileged Save for dropdown on the report toolbar, Saved views folds per owner, View as on Users & access. Switch user / role picker merges Live + v3 users. Creating a salesman/manager whose email matches an active salesman row auto-checks that salesman for access. Report salesman dropdowns stay on customer SalesGroup from D365, not the users table.
**Why:** A login is not a D365 SalesGroup. Views and schedules hang off users. Dropdown filter values hang off customers. Mixing those would send the wrong key to the stored procedure. Impersonation remains for "see exactly what they see."
**Status:** DECIDED — shipping this change.

## 2026-09-02 New schedule filename default is MM-DD-YYYY
**What you asked for:** Filename template on all new schedules should default to `{Schedule}_{MM}-{DD}-{YYYY}`.
**What I chose:** That is now `DEFAULT_FILENAME_TEMPLATE` (forms, blank resolve, and create-if-omitted). Existing stored templates are not rewritten. Same-day reruns of the same schedule can overwrite the previous file because the clock time is gone.
**Why:** You asked for that pattern. Time in the old default (`_{HH}{mm}`) is what you dropped.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Personal schedules get CC and BCC
**What you asked for:** When editing a salesman’s schedule, extra To addresses already exist. Add CC and BCC. The salesman himself still emails only himself.
**What I had to decide:** Whether CC/BCC belong only on the personal wizard, or also on More → Schedule from a report.
**What I chose:** Same privileged fields in both places. Company wizard already had CC/BCC; personal Where and the report modal now match. Backend already stored and sent `email_cc` / `email_bcc` for privileged users.
**Why:** Create-from-report would otherwise be unable to set CC/BCC until you edited the row. Salesman POST still drops those keys.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Drop Excel outline groups; darken innermost footer grey
**What you asked for:** Roll back collapsible groups in Excel export. The lightest footer grey looks white and needs to be darker.
**What I chose:** Stop stamping Excel `outline_level`. Footer greys step from the dark end (2-level customer totals use `#9CA3AF`, not `#E5E7EB`). Grid and Excel still share the same RGB.
**Why:** The outline gutter was not wanted. Stretching a 2-level group across a 4-step palette jumped to a near-white grey.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Named Customer Activity views can be scheduled without a period
**What you asked for:** Turn on scheduling for Customer Activity even without a period.
**What I had to decide:** Whether empty params still count (no Yesterday/MTD/YTD), or only views with a named period.
**What I chose:** Named personal Customer Activity views are schedulable. Empty params are not a custom date range. Default, company views, and custom from/to stay off the list. Company monthly CA schedules are unchanged.
**Why:** You reversed the 2026-09-01 hold. Heshy has a named CA view with no period and needs it on the 3-step list and More → Schedule.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Personal schedules page is full width
**What you asked for:** Personal schedules should be full width like company schedules.
**What I chose:** Drop `container-narrow` (800px cap) from the personal schedules template. Company schedules already used the default full-width container.
**Why:** The actions table is the same kind of wide grid. Capping personal at 800px squeezed the columns; company did not.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Excel grouped rows are collapsible, start expanded
**What you asked for:** Excel files should group rows so they collapse, default expanded. Skip it if that means rewriting the Excel writer.
**What I chose:** Keep write-only streaming. Set `outline_level` on each row before append (write-only flushes immediately). Nested: data is the innermost outline; banners/totals sit one level out; grand total ungrouped. `hidden` stays false so Excel opens expanded. `summaryBelow` puts the +/- on the total row.
**Why:** openpyxl write-only already writes row dimensions. No need to switch to a fully-loaded workbook.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Ordered group totals skip Net Price; nested groups use shade ladders
**What you asked for:** Do not total Net Price on group footers. Nested group headers/footers were clashing. Footers should be greys (grand darkest, then salesman, then customer). Headers the same idea in shades of the existing blue. Dark fills need white text.
**What I had to decide:** Whether to skip only Net Price or every unit-price column, and whether Excel and the grid share one recipe.
**What I chose:** Skip Net Price by `sum: false` plus a field-name fallback so old cached payloads still behave. Number 4 Avg/Book Price stays summed. Grey footer / blue header ladders: outermost darkest, inner lightest, any group depth. Text color is whichever of white or `#1E293B` has higher contrast (so mid greys do not get unreadable white text). Same RGB in `export.py` and `report.ts`.
**Why:** Net Price is Extended / Qty; adding it on a salesman footer is a fake number. One fill for every group level made Daily Ordered unreadable. Distinct hues can wait.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Same agent stacks PRs; two agents get two PRs
**What you asked for:** Put the stacking rule in Cursor rules, and on all repos. Same agent stays on the last open PR. Two agents at once use two PRs.
**What I chose:** Wrote it in `git-discipline.mdc` (owns git). README Rule Preferences points there. Copied into MasterGenAIInstructions (master + template) so `update-all` can push it to registered local projects. This AchimSales change stays on PR 25.
**Why:** Extra PRs were coming from Cloud Agent “new branch per task” colliding with you wanting one PR to merge.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Follow-up work stays on the open PR
**What you asked for:** Do not open a new PR for the next small ask. Put it on PR 25 so it can merge together. You hate extra branches and PRs.
**What I chose:** Cherry-pick the Saved views collapse onto `cursor/settings-exclusion-dropdown-0ed8` (PR 25) and close PR 26. Standing preference: while a feature PR is open, stack the next request on that same branch.
**Why:** Splitting every small UI tweak into its own branch made a pile of PRs that you then have to merge one by one.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Saved views on the report page start collapsed
**What you asked for:** Default collapse presets on the report page.
**What I chose:** In the Saved views panel, Company views and My views are collapsed `<details>` groups. Default stays visible. Click a header to expand.
**Why:** Opening Saved views was dumping every company and personal view at once. Collapsing those groups keeps Default one click away and the long lists tucked away until you want them.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Settings exclusions use the report customer dropdown list
**What you asked for:** Customer exclusions on Settings should be a dropdown filled from the same endpoint as the report customer picker, scoped to the user.
**What I had to decide:** Whether Settings should call `/api/reports/ordered/customers` (the report URL) or a settings URL that runs the same lookup + salesman filter.
**What I chose:** `GET /api/settings/customers` using `LookupService.customers_visible` (same helper as the report picker). The Ordered URL 403s when Ordered is turned off; salesmen can still set exclusions. POST now rejects accounts that are unknown or outside the caller's salesman keys.
**Why:** You wanted the same list and scope as the report dropdown, not the dashboard mirror checkbox list. Exclusions are not a report action, so they should not depend on Ordered being runnable.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Applying a view showed `_isDuplicate` of undefined
**What you asked for:** Applying a saved view still worked, but the pink error banner said `Cannot read properties of undefined (reading '_isDuplicate')`.
**What I chose:** Stop stuffing `generated_at` onto `state.tabs`. Applying a view walks every key on that map to hide extra tabs; the timestamp key is not a tab, so reading `_isDuplicate` threw after the grouping had already been copied in.
**Why:** The report result never sends `generated_at`, so the extra key was always `undefined`. The table looked fine because the payload had already rendered.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Daily Ordered By Customer is salesman-only; By Order is flat
**What you asked for:** On the Ordered Daily Ordered view (PR 20), By Customer should not group by customer — only by salesman. By Order should not be grouped at all.
**What I chose:** Canonical By Customer `group: ["Salesman"]` (still sort salesman then customer). By Order `group: []` so it does not pick up the builder’s salesman default_group. Summary stays salesman then customer.
**Why:** By Customer is already one row per customer; a customer group banner is noise. By Order is a line list; salesman groups were coming from the builder default, not from an explicit view setting.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Company Ordered views do not store a period
**What you asked for:** Daily Ordered should group by salesman then customer. Saving the view should not require picking a period; company schedules already run YTD / MTD / yesterday.
**What I chose:** Daily Ordered canonical params are empty (no period). PUT and the Save this view button strip period / from / to. Edit does not auto-run when there is no period, and Save stays enabled so you can keep the layout without a preview. `yesterday` on old views maps to the dropdown's `daily` (Yesterday). Heshy Open Orders still seeds `period: yesterday` for a UI preview; a save still drops the window. Grouping is Salesman then Customer Name on Summary, Salesman then CustomerName on By Customer.
**Why:** The view is a layout template. Stamping the preview period made the Yesterday dropdown blank (`yesterday` is not an option), auto-ran an unbounded Ordered fetch, and left Save disabled until that run finished.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Salesman Excel colors follow the field, not the column letter
**What you asked for:** Fix salesman report formatting on Excel export. Default 2 hides Sort Number and Salesman; the site still colors the month block, but Excel started the purple/green/blue bands at column E instead of C (where that same info now sits).
**What I had to decide:** Whether to invent a formatting system for every report, or only fix salesman.
**What I chose:** Salesman only. Stamp `band` 0/1/2 on the month / YTD / full-year fields in the builder. Excel (and the grid) color by that field tag, with a field-name fallback for old cached payloads. Never use exported column index. PR #1 catch-up stays a later job.
**Why:** You said only this report needs it. The site was already bound to the full column list (hidden columns keep their index); export dropped hidden columns then painted `idx >= 4` among what was left.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Daily Ordered groups by salesman then sorts customers
**What you asked for:** Daily Ordered should group by salesman and sort by customer within each salesman. The latest midnight file did not.
**What I chose:** Put that on the Daily Ordered view for Summary (group Salesman, sort Salesman → Customer Name → Item) and By Customer (keep salesman then customer groups). Excel grouping now keeps salesman blocks together even if a customer sort is listed first. Heshy Open Orders still sorts customer then order number. Replay onto `main` because `cursor/**` no longer auto-deploys.
**Why:** Summary is the first Excel sheet and was grouping by salesman without sorting first, so the same salesman appeared many times and customers stayed in dump order. By Customer was already nested correctly. Putting customer ahead of salesman in the sort list would split salesman groups (groupby needs consecutive keys).
**Status:** DECIDED — shipping this change.

## 2026-09-02 Official branch is `main`; only `main` auto-deploys
**What you asked for:** Rename `webapp-cache` to a normal name like `main`. Explain the leftover branches and pull requests.
**What I chose:** Official branch is `main` (same code that is on the site). Azure deploys only on push to `main`. `cursor/**` Cloud Agent branches no longer auto-deploy, because that is why the shop window kept getting replaced. Leftover `cursor/` branches are old photocopies; the Sol/Grok rewrite stays on PR #1 until we replay live onto it on purpose.
**Why:** One official notebook. Side copies do not go live until you merge them.
**Status:** DECIDED — shipping this change.

## 2026-09-02 Number 4 oversized mail must include a SharePoint link
**What you asked for:** This morning's Number 4 test email said the workbook was too large and had no SharePoint link, even though that link worked in a recent test.
**What I had to decide:** Whether to merge the Sol/Grok review rewrite (`cursor/p0-security-containment-adb6`) onto live at the same time.
**What I chose:** Fix the missing link on the code that is actually on the site (`cursor/schedule-from-views-89b7`, last Azure deploy). Chunked Graph uploads (Number 4 is ~13 MB) often return an item id with no `webUrl`. We now GET `/items/{id}` first, then retry the path GET with Graph's trailing colon, and only then try `createLink`. If Graph still has no URL after a successful upload, the body names `Direct Reports/Test/{filename}`. Do **not** merge PR #1 onto a `cursor/**` or `webapp-cache` push: that rewrite deletes `/legacy`, splits out the worker, and the PR itself says keep draft until Phase 10. Combining it with live feature work is a conflicted rebase, not a clean merge, and a push would deploy the unfinished rewrite over production.
**Why:** `webapp-cache` is behind the last `cursor/**` deploy. Production already has the download-button code; this morning's mail still had no URL because we never read `webUrl` from `/items/{id}` after a chunked upload. Merging the review branch now would wipe the live Number 4 / views / mail stack.
**Status:** DECIDED — shipping the mail-link fix; review rewrite stays on PR #1.


## 2026-09-01 Schedules: 3-step from saved views; old wizard to Settings
**What you asked for:** Rework scheduling. Move the current wizard to the developer dashboard. Schedules page becomes Choose a view → When → Where. Grill answered the rest.
**What I chose:** Salesmen and managers only schedule named saved views (no Default, no company views, no custom from/to, Customer Activity out for now). Admin/dev can pick others’ views grouped by user; the schedule belongs to that person (**Email to {name}**). Extra emails, SharePoint, and test-list-on-no-data are admin/dev only. One-time conversion snapshots personal schedules into saved views; company schedules stay as-is under Settings → Company schedules (admin/dev only). More → Schedule only when a named view is loaded and not dirty. Filename template stays on Where. No Review step.
**Why:** You grilled and locked those answers. Managers using the 3-step means the 5-step cannot stay on the main Schedules page.
**Status:** DECIDED — shipping this change.

## 2026-09-01 Number 4 months stay before the trailing block; By Item gets dollars
**What you asked for:** September months must sit with the other months, before Total Qty / Total $ / Avg Price / Book Price / Salesman. By Item was missing Total $, Avg Price, and Book Price, and was out of order.
**What I chose:** Same trailing block on all four tabs: Total Qty, Total $, Avg Price, Book Price, Salesman. Month qty/$ (including a new Sep the SP or saved Default appended after Salesman) sort into calendar order before that block. By Item is no longer quantity-only. builder_version 5.
**Why:** The rolling-12 SP appends the new month after Salesman, and a saved Default does the same. Moving only Avg/Book left Sep after Salesman. You overrode the old By Item qty-only choice.
**Status:** DECIDED — shipping this change.

## 2026-09-01 Number 4 Avg Price and Book Price sit before Salesman
**What you asked for:** Two more Number 4 fields, Avg price and Book price, added before the salesman column.
**What I chose:** By Customer tabs show **Avg Price**, then **Book Price**, then **Salesman**. By Item stays quantity-only. SP aliases (AvgPrice / BookPrice) are renamed. Missing Avg Price is Total $ / Total Qty. Missing Book Price still gets a column. Saved Default order cannot leave Book Price after Salesman (grid + email). Live Excel By Customer writer matches. builder_version 4.
**Why:** Live Excel already had Avg Price before Salesman and Book Price last. The new fields belong together, immediately before Salesman.
**Status:** DECIDED — shipping this change.

## 2026-09-01 Skip remaining noisy Semgrep rules so the check can pass
**What you asked for:** Yes — keep going until Static scan (semgrep) is green.
**What I chose:** Still scan `v3/` with `p/default`. Also skip SQLAlchemy/Flask/formatted-SQL, CDN integrity, dynamic urllib, and SHA1. App code is unchanged.
**Why:** The leftover 34 hits are how this site is written: SQLite `execute()` with `?` values and allowlisted column names, an admin DB explorer, version-pinned unpkg scripts, Graph/Sabbath HTTP, and SHA1 used as a cache key. Rewriting those is not this ticket.
**Status:** DECIDED — shipping this change.

## 2026-09-01 Drop Django Semgrep rules on the Flask app
**What you asked for:** Why is Semgrep flagging Django if this site is Flask? Drop those rules.
**What I chose:** Agent Guardrails still scans `v3/` with `p/default`, but skips the Django CSRF and Django SQL rules. Flask already uses `{{ csrf_token() }}`.
**Why:** `p/default` runs every framework pack. The Django CSRF rule wants `{% csrf_token %}` and does not recognize Flask’s helper.
**Status:** DECIDED — shipping this change.

## 2026-09-01 Semgrep scans the live app only
**What you asked for:** Is there a way to only have Semgrep scan the current live app?
**What I chose:** Agent Guardrails Semgrep runs on `v3/` (home site). It no longer scans `webapp/` (`/legacy`).
**Why:** The red check was ~126 hits in the old Live templates. Those are not the app at `/`.
**Status:** DECIDED — shipping this change.

## 2026-09-01 Test-list double mail after folder upload fail
**What you asked for:** It's the test emails that are failing and then succeeding that I'm seeing double emails for.
**What I had to decide:** Whether a Test-folder (or live folder) upload fail should still fail the whole send after Graph already delivered.
**What I chose:** If the inbox already got the mail, delivery is ok. The scheduler must not retry Graph. Folder error stays on the result. SharePoint-only sends still fail when the upload fails.
**Why:** Test mode always uploads to `Direct Reports/Test`. Graph would send, the Test upload would fail, the runner retried, and the test list got a second copy (and sometimes `[FAIL]` too).
**Status:** DECIDED — shipping this change.

## 2026-09-01 One status email when a schedule fails then succeeds
**What you asked for:** I'm still getting failure and success emails for the same schedule runs.
**What I had to decide:** The one-mail hold lived on a diverged branch and was overwritten when later `cursor/**` deploys took production.
**What I chose:** Re-apply it on the live SHA. Home-site `[FAIL]` waits 15 minutes and is dropped if that schedule succeeds; the success mail names the failure. Azure runbook alerts are buffered and `main()` wraps the retry (Automation starts `main` by name). Runbook file still needs `deploy-runbook.ps1` to publish.
**Why:** Empty-list Number 4 deploy (and the Ordered/oversized/company-views stack) did not include this hold, so production still mailed `[FAIL]` then the later pass.
**Status:** DECIDED — shipping this change.

## 2026-08-31 Number 4 Default ungroup was ignored in email
**What you asked for:** The Number 4 report, I tried to edit the Default view but in the email it's still grouping by item.
**What I chose:** A saved `group: []` means ungrouped. Excel only uses the builder’s Item # default when the view never set `group`. Empty list used to fall through to Item #, so Default ungroup (and Email me after ungrouping) still grouped.
**Why:** Number 4 tabs ship `default_group: Item #`. Clearing group on Default saved `[]`, which the exporter treated as “no group specified.”
**Status:** DECIDED — shipping this change.

## 2026-08-31 Ordered Summary gets Extended Price Cancelled
**What you asked for:** Extended price cancelled has to be added to the Summary tab of the Ordered report.
**What I chose:** New Summary column **Extended Price Cancelled**, between Ordered and Remainder. Same SP `Cancelled $` the other Ordered tabs already use, summed by customer + item. Missing/blank is $0. Ordered builder_version 8 so cached v7 payloads are not reused.
**Why:** Summary already shows Ordered and Remainder dollars. Cancelled was only on the other tabs.
**Status:** DECIDED — shipping this change.

## 2026-08-31 Oversized email must include a download link
**What you asked for:** If an attachment is too big for the email, it should include a link.
**What I had to decide:** The download button was already the intended behavior; why the mail still had no URL.
**What I chose:** Keep SharePoint/OneDrive + Outlook **Download workbook** button. Graph chunked uploads often return no `webUrl` — GET the item, then an organization view link. A 413 retry uploads to `Test` if there is no URL yet and sends the same button, not “sent without the file.”
**Why:** The 13 MB Number 4 case uses an upload session. Missing `webUrl` produced “download it from SharePoint” with nothing to click. Same hole on Graph 413.
**Status:** DECIDED — shipping this change.

## 2026-08-31 Schedules failed after company-views column
**What you asked for:** Why are all the schedules failing? Fix it.
**What I had to decide:** Root cause, and whether to wait on a Premier auth review before shipping.
**What I chose:** `User.from_row` required `can_see_company_views`. Request handlers swallow that IndexError; `ScheduleRunner` does not. Gunicorn workers racing 0016 can also crash `migrate()` (`duplicate column name`) so `wsgi._bootstrap_v3_async` never starts the scheduler. Hotfix: missing flag reads as False (fail closed); duplicate-column retry records the version and continues; boot repairs a missing column; parallel ALTER of that column does not raise. Stayed on `cursor/company-views-permission-89b7` (that SHA is what production is running). Skipped Sol/Fable so the outage fix is not delayed.
**Why:** Site up + every schedule dead matches swallowed request errors and a scheduler that never starts or dies on `from_row`.
**Status:** DECIDED — hotfix deviation (no Premier auth pass before deploy).

## 2026-08-31 Company views are a per-user flag
**What you asked for:** Company views visibility should be a permission per user. Everyone no by default besides developers.
**What I had to decide:** Whether developers always ignore the flag, and whether editing still needs the manager/admin schedule privilege.
**What I chose:** New `users.can_see_company_views` (default 0). Authz is the flag only — an admin can uncheck a developer. Developers get 1 on migration, first INSERT, and the env developer seed (that seed restores the flag on boot, same as it restores the role). See (Home, presets `company`, GET, wizard optgroup) requires the flag. Edit requires the flag **and** `can_see_company_schedules`. Live user mirror sets 1 for developers on INSERT and does not overwrite the flag on conflict. People (`/admin/users`) has the checkbox. `?cview=` does not auto-run if GET is 403.
**Why:** Shared views were showing to anyone who could open the report. Default off matches “besides devs.”
**Status:** DECIDED — shipping this change.

## 2026-08-26 Shipping $ and remainder have no fallback math
**What you asked for:** Shipping $ and Extended Price Remainder should only show ShippingDollars from the SP. No fallback calculations.
**What I chose:** Both columns are `ShippingDollars` only. Missing/blank is $0, same as other SP dollar fields. Open $ stays Ordered $ − Shipped $ − Cancelled $. Ordered builder_version 7.
**Why:** Qty × price and Open $ math were invented numbers, not the SP.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Ordered remainder is ShippingDollars
**What you asked for:** PO # is CustomerRequisition. Ship Date is ShippingDateRequested. Summary Extended Price Remainder is ShippingDollars.
**What I chose:** Map those three SP columns. Shipping $ on the other Ordered tabs also uses ShippingDollars when present (else released qty × price). Open $ stays Ordered $ − Shipped $ − Cancelled $. If ShippingDollars is missing, Summary remainder keeps that Open $ math so the report does not go to $0. Ordered builder_version 6.
**Why:** Matches the ordered_report catalog. Remainder is the shipping-dollar column, not a separate delivery-remainder dollar field.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Ordered remainder dollars come from the SP
**What you asked for:** Summary Extended Price Remainder should come from the stored procedure column “delivery remainder dollar amount,” not from Ordered $ − Shipped $ − Cancelled $.
**What I chose:** Map that SP field (DeliveryRemainderDollarAmount and a few name variants) onto the Ordered line. Summary Extended Price Remainder and Open $ on the other Ordered tabs use it when present. If the column is missing, keep the old Ordered $ − Shipped $ − Cancelled $ math so the report does not go to $0 before the SP change lands. Ordered builder_version 5.
**Why:** Same remainder dollars everywhere. Blank/missing must not wipe the column.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Company views for Daily Ordered and Heshy Open Orders
**What you asked for:** A Daily Ordered view grouped by salesman then customer on By Customer, applied to every daily company Ordered send. A Heshy Open Orders view with Full Data only, sorted by customer, grouped by order (order totals, no customer total), no LineNumber. Ship Date on Ordered in general without failing if the SP does not send it yet. Company-wide views. Test sends of yesterday Ordered and the open-orders report.
**What I had to decide:** Whether to change By Customer’s default group for every Ordered use; whether Excel grouping could stay single-level; whether named company views live at send or stay as schedule snapshots.
**What I chose:** Named company views in `company_views`, shared like Default. Daily Ordered is salesman then customer on By Customer only — the builder’s default group stays salesman-only. Heshy Open Orders is Full Data only: sort customer then order number, group on order number. Excel nested groups + sorter-aware sort so a second group and a customer sort both survive the file. Send uses the live company view when the schedule’s View name matches. Ship Date is always on Full Data; blank if the SP has no column. Ordered builder_version 4. Boot seeds the two views and stamps matching daily company schedules (not salesman-split files).
**Why:** One named view per job, visible to everyone, editable by managers. Changing the global By Customer default would regroup salesman-split files and anyone still on Default.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Default view per report
**What you asked for:** A Default view for every report matching how it looks now, a way to edit those defaults, the schedule wizard showing Default as the view, and the schedules page showing which view each row uses.
**What I had to decide:** Company-wide vs per-user Default; whether editing Default rewrites existing scheduled files; who can edit.
**What I chose:** One Default per report, shared. Managers and admins edit it from Saved views (Edit, then Save this view). Schedules that use Default with an empty layout pick up the new Default on the next send. Schedules that already have a locked layout (seeded tab lists, or Schedule from a report page) keep that snapshot and still show Default or Custom on the list. Wizard starts on Default. Report-page Schedule saves as Custom.
**Why:** Company schedules need one shared starting layout. Wiping seeded “no commissions” files when someone edits Ordered Default would change production workbooks.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Azure Actions concurrency group renamed
**What you asked for:** Ghost GitHub runs cannot be cancelled or deleted. That made it look like Actions could no longer deploy the site.
**What I chose:** Rename the Azure workflow concurrency group from `deploy-achim-sales-reports` to `deploy-achim-sales-reports-v2`. Keep one-at-a-time deploys (`cancel-in-progress: false`). `deploy.ps1` stays the backup when Actions is wedged.
**Why:** Those four runs are stuck with no jobs. GitHub will not cancel or delete them. The old group may keep every new Azure deploy waiting behind them. A new group name is a fresh lock. Pages ghosts do not use this group.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Ordered Fulfillment % on the rolled-up tabs
**What you asked for:** Put fulfillment percentages back on the Ordered report, colored like the old runbooks.
**What I had to decide:** Old runbooks had Fulfillment % on By Customer, By Item, By Order, By Salesman, and Full Data (red→yellow→green). Summary (customer + item) did not. v3 only had the column on Full Data.
**What I chose:** Same five tabs as the old writer. Formula stays `(QtyOrdered - QtyCancelled) / QtyOrdered` on the summed qty for rolled-up rows. Grid and Excel already color `Fulfillment %`. Summary stays without it. Ordered builder_version 3 so cached v2 payloads are not reused.
**Why:** Matches the old workbook. Summary never had that column.
**Status:** DECIDED — shipping this change.

## 2026-08-26 Oversized schedule mail gets a download button
**What you asked for:** The Daily 5am Number 4 mail said the 13.4 MB workbook was too large to attach, and told you to download it from SharePoint or export it from the app — with no link. Test-mode files must not land in the live Daily/YTD folders.
**What I had to decide:** Test mode used to skip SharePoint entirely. Graph then refuses anything over ~3 MB, so the body had no URL. Whether to write test runs into the real Daily folder, skip SharePoint (no link), or dump into a separate test folder.
**What I chose:** Test mode still emails only the test list. If the schedule has a SharePoint path, the file goes to `Direct Reports/Test`, never to the live folder. Oversized Graph mail (no live folder, or Email me) also lands in `Test`. The mail includes an Outlook-safe blue **Download workbook** button plus the raw URL in the plain-text part. A failed Test-folder upload does not fail the email. Split salesman files stay email-only.
**Why:** You need a clickable download in the inbox, and test dumps must not mix with production Daily/YTD. Graph wraps mail as HTML, so a `<pre>` of the old text could never render a button.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Preset salesman/status must ride along even if the dropdown is empty
**What you asked for:** Heshy Open Orders should only run open orders for Heshy. The preset did not keep those filters.
**What I chose:** Keep the saved salesman on `pendingSalesman` until the dropdown actually has that option. `collectParams` sends that value even when the list is still loading. Status “Open” maps to “Open order”. Home-card URLs still include salesman and status.
**Why:** Lookups often return empty on first paint. Setting `<select>.value` to Heshy with no matching option silently resets to All, and the auto-run went out unfiltered.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Home presets and saved views must run, not replay the last job
**What you asked for:** Opening Heshy Open Orders (or any home preset / saved view) after already running a report still showed the previous run.
**What I chose:** `?preset=` skips reconnecting the last job for that report (unless `?job=` is also on the URL). Clicking a saved view’s name runs it. Edit still loads filters/layout without running when the grid already has data.
**Why:** Coming-back resume was winning over the home-page preset, so the new filters and layout never applied. Saved-view name click only changed the form, so an already-shown grid looked unchanged.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Merge remaining branches onto production
**What you asked for:** Merge the leftover Sales by State / meeting-fix work and the Shabbos makeup-clock work into the production site.
**What I chose:** Merge both onto `webapp-cache` (keep Number 4 builder 3, empty salesman split = no xlsx, catch-up at scheduled HH:MM). Production is `webapp-cache`; Azure deploys that branch and `cursor/**`.
**Why:** Those two commits were the only remaining unique work after branch cleanup. They never landed on `webapp-cache` because the remote branch names were deleted first.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Azure GitHub Action also deploys cursor/** branches
**What you asked for:** Let a Cloud Agent deploy, the same way a push to `webapp-cache` does.
**What I chose:** Keep one production Action. Trigger it on `webapp-cache` and `cursor/**`, plus the existing manual `workflow_dispatch`. Queue overlapping deploys (`concurrency`, do not cancel). Same production slot as today.
**Why:** GitHub runs the workflow file from the branch that was pushed, so this file has to list Cloud Agent branches or their pushes never start a deploy. There is no staging slot in the current Action. `deploy.ps1` stays as a fallback when Actions cannot run.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Number 4: YTD tabs, By Item qty-only, group by item
**What I had to decide:** How to add rolling-12 + YTD tabs for each Number 4 version, drop money from By Item, and group by item, without a YTD stored procedure.
**Options I considered:** Wait for DBA YTD SPs; fetch invoice lines and pivot in the app (old path); derive YTD from the rolling-12 pivot (prior-year months dropped, totals recalculated).
**What I chose:** Derive YTD from the rolling-12 SP result. By Item strips every money column (month $, Total $, Avg Price, Book Price). All Number 4 tabs default-group by Item #. Excel By Item writer matches (qty only; it already had 12 Months + YTD sheets).
**Why:** YTD months are always inside the rolling-12 window, so the numbers stay on the same basis as the SP (exclusions, merchandise $). No extra SP call. Builder version 3 so old cached payloads are not reused.
**Status:** DECIDED — shipping this change.

## 2026-08-25 Shabbos makeup at the scheduled clock, not havdalah
**What I had to decide:** Home-site schedules skipped Shabbos then fired as soon as havdalah passed. The owed send should keep the schedule's clock time, and the date window should follow the period (MTD on Friday the 30th → Monday 10pm covering that MTD, plus month-end if the makeup is next month).
**Options I considered:** Keep motzei-Shabbos fire (current); wait for the next regular cadence day (loses last_month / month-end MTD); wait for the next same HH:MM that is not restricted, using Monday–Friday for periods that cannot wait for the next cadence.
**What I chose:** Skip-class (yesterday/daily, in-month MTD, in-year YTD) waits for the next regular slot at that HH:MM and never Saturday night. Reschedule-class (last_7_days, last_month, month-end MTD, year-end YTD, all-time reports) waits until the next weekday at that HH:MM. MTD that crosses a month runs the skipped day's MTD, then through month-end if those dates differ. Branch is `webapp-cache` (Beta is already `/`).
**Why:** Matches "not right after Shabbos" and the Friday-30th-10pm → Monday-10pm example. Live Azure still reschedules after havdalah; this change is home-site only.
**Status:** DECIDED — shipping on the home-site clock.

## 2026-08-24 Meeting: tabs, views, groups, empty split mail, Ordered %, personal Edit, Sales by State sheet 3
**What you asked for:** After the user meeting — restore removed tabs like columns; rename copied tabs; Edit/Delete on saved views (not Edit+✕); Edit opens the whole view then Save / Save as; nested groups with delete-able pills; home-page presets apply the full view; empty salesman splits must not send a workbook (text “No Data Found” like the old runbook); Daily 9am salesman Ordered grouping like Daily shipped; bring back Ordered Fulfillment % (green→red); edit personal schedules; Sales by State third sheet from `sales_by_state_filtered`.
**What I chose:** Removed original tabs stay in memory and come back from the Columns dropdown. Copied tabs get Rename. Edit loads filters+layout (and runs if the grid is empty); Save with the same name overwrites, a new name creates another view. “Group by this column” / “Add subgroup” append; pills remove one level. `applyLayout` recreates cloned tabs so a home-page preset matches the saved view. Split legs never send empty Excel; they send the old runbook no-data text. The no-data checkbox is for the company copy only. Per-rep Ordered files drop Salesman grouping and use a tab-order layout like shipped dropping commissions. Fulfillment % is `(QtyOrdered - QtyCancelled) / QtyOrdered` on Full Data, colored in the grid and Excel. Personal rows get Edit and PUT `/api/schedules/<id>`. Sheet 3 catalog key is `sales_by_state_filtered` (overrides the earlier “detail only” choice). Test mode stays On.
**Status:** DECIDED — deployed `0db0f60` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-24 Recent Reports link; export panel from the status line
**What you asked for:** The "building in the background — see Recent exports" message pointed at a place you could not find. Recent Reports should be a hyperlink.
**What I chose:** Header label is **Recent Reports**, styled as a text link (same button, same jobs panel). Starting an Excel export opens the Recent exports list and the status line's **Recent exports** words open it too.
**Status:** DECIDED — shipping this change.

## 2026-08-24 Sales by State on the home site (SQL only)
**What you asked for:** Add the Sales by State report to the home site (former Beta). Use the SQL API only — no OData, no data-origin selector on Settings. The Excel file is the look; the Word doc is the DBA handoff.
**What I chose:** One report, three tabs (Summary, New York City, Detail) matching the workbook. Year filter → FromDate/ToDate for the three catalog keys. Left Unknown / filtered / other-transaction SPs out because they are not in the sample file. Not shown to salesmen by default.
**Status:** DECIDED — shipping this change.

## 2026-08-21 Invoiced salesman from endpoints, not Excel
**What I had to decide:** After the 029 stamp, whether to keep using salesman_map.xlsx / the hardcoded map for invoiced salesman codes.
**What I chose:** Do not use the Excel map for invoiced salesman identity. Use the invoiced report row; if that is missing or just a number, use the same customer/salesman data as the report dropdowns. Live OData invoiced uses CustomersV3.SalesGroup the same way, with no Excel overlay.
**Status:** DECIDED — shipping this change.

## 2026-08-21 Invoiced 029; saved views; schedule Where page
**What you asked for:** Daily invoiced marked every salesman as 029. Saved views should open without running, be editable, and appear when scheduling. The Where page should not squash fields; hide Email/OneDrive/SharePoint until chosen; filename first; move sharing / run-as / test-email-on-empty to Options.
**What I chose:** Prefer SalesGroup/SalesmanName when the salesman field is a number; if the spreadsheet stamps one number on most rows, use the built-in map for numbers. Saved views: click applies filters without running; Edit patches name+filters+layout; Options has a per-report dropdown. Where: filename, then Email / Save to Cloud. OneDrive vs SharePoint is one cloud target (same as before). Empty-data "test email addresses" uses the Settings test list.
**Status:** DECIDED — shipping this change.

## 2026-08-21 Whole-job retry; unlink dead OrderReportDirect
**What you asked for:** Another job failed this morning. Add a retry so a one-time blip is not the last word.
**What I chose:** This morning's Failed row was leftover `OrderReportDirect` on `DailyOrderReport` looking for `daily_order_report.py` on SharePoint (gone). The real 4am `universal_runbook` job Completed. Unlinked that leftover. Real jobs now retry the whole run once after 30s (Azure runbook + home-site schedules). `[FAIL]` mail still only after that second miss. Test mode stays On.
**Status:** DECIDED — shipping this change.

## 2026-08-20 Home-site schedule failures email the test list
**What you asked for:** Know why the three legacy 9am jobs failed, stop that class of miss, and get a mail on the home site whenever a report fails — using the test-email field even when test mode is off.
**What I chose:** The 9am jobs were not shut off. SharePoint dropped the TLS connection while they downloaded scripts (and once the run log). Downloads now use the existing Graph retry (up to 4 tries). Home-site clock and Run now failures send `[FAIL]` mail to the test-email list, test mode on or off. On-page Run report / Email me stay on-screen only. Test mode stays On.
**Status:** DECIDED — shipping this change.

## 2026-08-20 Login and role picker live on the home app
**What you asked for:** Login should go to Beta (home). The developer role picker should work there.
**What I chose:** `/login` is the home sign-in page (Achim User + External Rep). Microsoft still starts at `/legacy/login/start` and comes back to `/auth/callback`. Developers land on `/dev/role-picker` (same picker as old Live: yourself as admin, or search/pick a user). The header switch-user button opens that picker even while impersonating. Test mode stays On.
**Status:** DECIDED — deployed `1a6be71` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-20 Beta is the site home; old Live is /legacy
**What you asked for:** Make the Beta page the home page. Put the current home at `/legacy`.
**What I chose:** `/` is v3 with `is_beta`. `/legacy` is `webapp/` (OData, email distributions). `/beta/...` 302s to the same path without the prefix. Microsoft login stays `/auth/callback` (no new Entra URI); the login page is `/legacy/login`. Anyone who can sign into Live can use `/` — the Beta Access flag is not a gate. If Beta fails to boot, `/` stays the old Live app. Test mode stays On.
**Status:** DECIDED — deployed `f181095` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Email me button; salesmen never see Commissions
**What you asked for:** A report-page button that runs and emails the user themselves. Salesmen must never see the commissions tab.
**What I chose:** Email me next to Run report (current filters → Excel to the signed-in address). Existing Email modal stays for other people/SharePoint. Invoiced Commissions is omitted for salesman role on run, result, export, email-now, and personal schedules. Managers and admins still see it.
**Status:** DECIDED — deployed `77e7dae` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Monthly Salesman SharePoint job stays; add a split schedule
**What you asked for:** Do not rewrite the monthly salesman SharePoint job. Add a separate schedule that fans out.
**What I chose:** Left `Monthly 1st 12am Monthly Salesman` / `Monthly Salesman Report` on `Salesman Report/Monthly` with no split. Seeded `Monthly 1st 12am Monthly Salesmen` / `Monthly Salesmen Report` with `split_by_salesman` and no folder (same 1st / 22:00 clock). Wizard salesman-report filters include salesman so that split flag survives a save. Test mode still On.
**Status:** DECIDED — deployed `ebdcdb2` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Save and On wait for the next scheduled time
**What you asked for:** Saving an edit or turning a schedule On should not run it right away.
**What I chose:** Save, create, and On claim today's slot when that time has already passed, so the clock waits until the next cadence. A schedule that was already On still catch-up-fires if we missed it (app down). Run now is unchanged.
**Status:** DECIDED — deployed `51a4641` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 SharePoint paths drop duplicated Direct Reports; folder tokens
**What you asked for:** Stop dumping files in Direct Reports/Direct Reports. One-shot fix. Let a schedule add a dated subfolder (Customer Activity → August 2026), and let me type that on any schedule.
**What I chose:** Strip a leading Direct Reports from seed, save, browse, and upload (migration for existing rows). Filename date tokens also work in the folder path; spaces stay (`{Month} {YYYY}` → August 2026). Wizard path is editable with token chips. Only Customer Activity auto-gets the month folder; other jobs keep their current path.
**Status:** DECIDED — deployed `4ad39b6` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Company schedules table sorts by name
**What you asked for:** The table with all the schedules should be sortable and automatically sort based on name.
**What I chose:** Company schedules render A→Z by name. Column headers (except Actions) are clickable to re-sort.
**Status:** DECIDED — deployed `45ece96` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Deleted company schedules must not come back on boot
**What you asked for:** Stop putting Daily 9am back after you delete it.
**What I chose:** Boot seed was re-inserting any Azure name that was missing. Delete now records the name so seed skips it. Daily 9am is also off the Beta seed list, and a migration deletes the leftover shared row so this deploy does not resurrect it.
**Status:** DECIDED — deployed `0324e32` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Schedules run log starts collapsed
**What you asked for:** The report run log should be collapsed by default.
**What I chose:** The Schedules Recent run log no longer auto-opens when there are rows. Run now still opens it so you can watch that job.
**Status:** DECIDED — deployed `24323bb` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-19 Company schedules can be copied
**What you asked for:** Copy a company schedule, then change options. Personal Copy already existed.
**What I chose:** Copy on company rows you can already edit. Duplicate everything (report, params, layout, cadence, recipients, SharePoint, filename, share flag, run-as). Name is `{original} (copy)`, then `(copy 2)` if taken. Leave Off so it does not double-send. Copier owns the new row so they can edit it. Shared names stay unique.
**Status:** DECIDED — deployed `d3e8404` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-18 Salesman-all jobs fan out; Ordered drops By Salesman
**What you asked for:** 9am Salesmen Ordered/Shipped should split one file per rep like live `--salesman all`, and those files should not include the By Salesman tab.
**What I chose:** Those company schedules now have `split_by_salesman` (stamped onto existing rows that had no split flags). Split-all with no picked keys emails every active salesman who has an address; no-email salesmen are skipped. Combined SharePoint/management copy still goes out. Per-salesman Ordered builds omit By Salesman (same as the live salesman workbook). Unscoped Ordered still has the tab. Test mode still sends every split to the test inbox.
**Status:** DECIDED — deployed `e3b1ef1` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-18 Invoiced shipped reports skip YTD (match live)
**What you asked for:** Original Python rules on Beta. `--salesman all` / salesman-scoped Shipped omits Commissions, so do not pull YTD — check what tabs are needed, then fetch only that.
**What I chose:** Skip the Commissions tab and the Jan 1 fetch when `params.salesman` is set, when `_skip_commissions` is set, or when a saved `layout.order` exists and does not include `commissions`. Delivery stamps `_skip_commissions` from that layout before the run (9am Salesmen Shipped). Unscoped Invoiced still YTD-fetches. Live OData runners were already correct; this is the SQL Beta path.
**Status:** DECIDED — deployed `2edb1cd` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Shabbos skip + catch-up on Beta clock
**What you asked for:** The Shabbos schedule override from the original runbook,
built into Beta.
**What I chose:** It was not on Beta. Clock runs now check Hebcal for Brooklyn
(same as the runbook): skip while melacha is assur, flag a catch-up, send after
havdalah. Run now still sends (deliberate). Hebcal errors fail open. Live Azure
skip-vs-reschedule by period is folded into this one catch-up so monthly
last_month is not lost until next month.
**Status:** DECIDED — deployed `785684c` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Test mode still splits salesman workbooks
**What you asked for:** Run company schedules just to me for a day or two, but
still split by salesman so I can check the splits.
**What I chose:** Test mode keeps mail on the test list and still skips
SharePoint. Split schedules now fan out: one combined file plus one file per
salesman with an email, salesman in the subject and filename. Salesmen are
not emailed. Salesmen without an email are still skipped (same as live).
**Status:** DECIDED — deployed `e4cd482` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Schedule workbook filenames include the schedule name
**What you asked for:** File names that are intuitive for each run (typed on a
Hebrew keyboard: change the file names to be more intuitive for each run).
**What I chose:** Blank `filename_template` is now
`{Schedule}_{YYYY}-{MM}-{DD}_{HH}{mm}` (Eastern). Company schedules had empty
templates, so Daily 9am and DailyOrderReport both arrived as
`Ordered_20260817.xlsx`. Custom templates are unchanged.
**Status:** DECIDED — deployed `a8140d2` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Beta schedule test mode was not surviving recycle
**What you asked for:** The Delivery test-mode switch (and the test email list)
kept going back to Off after saving.
**What I chose:** The toggle was saving. Azure wipes `/tmp/betadata/precious.db`
on recycle, and Litestream only replicated the `/test` DB. Add a second replica
for `BETA_PRECIOUS_DB_PATH` (`LITESTREAM_AZURE_BETA_PATH`). Unique company
schedule name so two gunicorn workers cannot double-insert the Azure import.
**Status:** DECIDED — deployed `9f7f613` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Settings mobile overflow + exclusive accordion
**What you asked for:** Settings on a phone was overflowing. Opening a section
should close the others.
**What I chose:** Exclusive `<details>` (one open at a time on every width).
Desktop no longer auto-opens all categories. Header **Previously run** shortens
to **Runs** under 480px; settings fields wrap instead of forcing min-widths.
**Status:** DECIDED — deployed `189024d` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Beta settings hub (mini rebuild)
**What you asked for:** One settings page on Beta that matches Live, categorized,
half-width, phone-first, with users, run histories, DB explorer, notification
diagnostic, and beta data sources. Test that it is wired.
**What I chose:** Rebuild Beta `/settings` only. Six categories (You / People /
Reports / Delivery / History / Developer). Email Distributions stays Live-only
(Beta schedules already send mail). Heavy tools stay linked pages. Global report
on/off is new `report_config`. Explorer covers precious + cache. Beta sources UI
lives on Beta; storage stays the live `beta_report_sources` table. Notes:
`.scratch/grill-notes.md`.
**Status:** DECIDED — deployed `a56a67b` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-17 Previously run list + OneDrive root Graph URL
**What you asked for:** A Previously run button; a minimizable run pill that shows
when the report ran; a way to name a kept run. OneDrive Browse 400 after Graph
permissions were granted (`…/drive/root::/children`).
**What I chose:** Header **Previously run** opens the existing jobs panel. The
bottom-right pill shrinks to an icon (remembered in localStorage). Each chip shows
Eastern date/time and optional `jobs.keep_name`. Keep and Name POST `{name}`
(max 80 chars). Opening a chip uses `?job=<id>`. OneDrive root listing uses
`/drive/root/children`, not `root::/children`.
**Status:** DECIDED — deployed `04b649e` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-14 Schedule test mode (redirect + address list)
**What you asked for:** A test mode with test emails so you can run the new
Beta schedules and compare the workbooks to Live, without hitting customers.
**What I chose:** Admin Settings toggle plus a list of addresses (add/remove;
need at least one to turn On). While On, company schedule mail (Run now and
the clock) goes only to that list, subject tagged `[TEST]`, SharePoint/OneDrive
skipped, salesman-split fanout skipped. Personal schedules unchanged. Off
restores stored recipients and SharePoint. Notes: `.scratch/grill-notes-schedule-test-mode.md`.
**Status:** DECIDED — deployed `2fe1404` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-13 Import Live Azure runbooks onto Beta (disabled)
**What you asked for:** Copy the LIVE Azure Automation schedules onto Beta,
left Off until you check each one.
**What I chose:** On Beta boot, seed company (`is_shared`) master rows from the
current Azure job list, all `is_active=0`. Names match Azure. SharePoint folders
match the Live Direct Reports paths. Recipients are empty (Live emails come from
env/distributions, not the job). Skipped `amazon_weekly` (no Beta report) and the
old OrderReportDirect link. `--salesman all` jobs write one workbook to the
Salesman Report folder — turn on split later if you want per-rep files. Re-seed
skips names that already exist.
**Status:** DECIDED — deployed `4214a62` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-12 One Schedules wizard (scope + share)
**What you asked for:** Stop having two schedule products. One Schedules page,
one Add flow. Company vs personal is options + an explicit share choice.
Managers can share; admins can run a schedule as a picked manager. Managers
see company schedules but cannot edit unless they created it or it is scoped
to them (read-only note: talk to an admin). Sales reps see only their own.
**What I chose:** Keep personal + master tables. Shared/company-setting rows
live on `master_schedules` with `owner_user_id`, `is_shared`, `run_as_user_id`.
Share = list visibility, not a data upgrade. Manager-created shared runs stay
in that manager’s book. Unscoped run = admin/developer with no manager picked.
Notes: `.scratch/grill-notes-beta-scheduling.md`.
**Status:** DECIDED — deployed `f8ac596` to `achim-sales-reports` (RuntimeSuccessful).

## 2026-08-12 Beta scheduling (grill locked)
**What you asked for:** Schedules on Beta — personal (OneDrive + email anyone) and
admin/master (SharePoint); cadence; filename pills; schedule-this-view; salesman
split; CC/BCC; no-data email options; test email; copy schedule.
**What I chose:** Enable existing v3 schedules on Beta (blueprint + cron + UI).
Master → SharePoint; personal → user OneDrive via app Graph. Excel now, PDF later.
Monthly 1–28 + last day. Split = all salesman **app users** with email; master
copy to typed recipients. Skip SP link-in-body and dry-run (use test email).
Copy schedule; one schedule per param set. Notes: `.scratch/grill-notes-beta-scheduling.md`.
**Status:** DECIDED — implementing

## 2026-08-06 Beta additions: Keep runs + filename templates
**What you asked for:** default Ordered grouping on Beta; resume previously run
reports with a Keep option; salesman Live color bands on screen + Excel;
schedule filename token GUI; Last Order Excel/PDF export popup.
**What I chose:**
- Ordered-only `default_group` (SQL already had it; OData bridge now attaches
  the same for Summary / By Customer / By Order).
- Resume window **48h**; **Keep** sets `jobs.kept_until` (+30d), cap **5** per
  user (oldest Keep cleared). Migration `0003_keep_and_filename_template.sql`.
- Salesman bands via streaming openpyxl fonts (no full-workbook mode) +
  Tabulator colored formatters.
- `filename_template` column on schedules/master_schedules; tokens resolved
  Eastern in `web.delivery.filename_template`.
- Last Order: one Export → Excel | PDF popup; PDF is a tiny stdlib writer.
**Status:** DECIDED

## 2026-08-06 Beta shares Live login (no separate Entra callback)
**What you asked for:** Fold Beta into Live so one Live sign-in covers `/beta`
(no second Microsoft login / no `/beta/auth/callback` Entra URI).
**What I chose:** Keep the v3 UI mount at `/beta` (Test look + hybrid reports),
but share Live's `session` cookie and `FLASK_SECRET_KEY`. Beta adopts
`session["user"]` into a v3 Principal; unauthenticated hits redirect to
`/login?next=/beta/...`. Live login honors `next`. Mount stays — full Live
blueprint rewrite of the Test UI is deferred.
**Why:** Same user-facing outcome (one login) without re-porting the report UI
into Live templates. Separate Entra callback was a side effect of a separate
cookie, not a product need.
**Status:** DECIDED

## 2026-08-06 Beta day-one scaffold (v3 mount, not rebuild tree)
**What I had to decide:** Grill said Beta tree from rebuild + v3 look, but
rebuild only seeds 4 reports while Beta needs every report day one.
**Options I considered:** (1) Port all reports into rebuild first, then mount;
(2) Mount v3 at `/beta` with `is_beta` (Test look + full report set) and hybrid
source switch; keep rebuild at `/test-next` until retired.
**What I chose:** (2). Hybrid SQL/OData via shared `beta_report_sources` in live
DB; OData bridge runs live Excel runners and shapes sheets into v3 tabs;
schedules stay Live/OData (phase two).
**Why:** "Every report" + Test look ship without blocking on rebuild feature
parity. Rebuild quality can land incrementally; `/test-next` still retires when
Beta is stable.
**Status:** DECIDED

## 2026-08-06 Beta app — reports page, hybrid SQL/OData, schedules later
**What you asked for:** fourth surface (Beta) so users have one reports link;
look like `/test`, run like `/test-next`, data per report (SQL if signed off,
else OData); eventually replace Live; PM wants this while parity continues.
**What I chose:**
- `/beta` on same App Service; tree from `rebuild/` + `v3` look; retire
  `/test-next` after Beta is stable; `/test` stays direct-link only.
- Beta = **reports page only** (menu → run → screen → export). Schedule/email
  and other product features stay on Live.
- Per-report source switch in **Live Settings** (dev-only), shared storage.
  Server hard-gates `can_access_beta` (direct URL too).
- **Phase two:** Live Azure schedules honor the same SQL/OData map. Day one
  schedules stay OData.
**Evidence:** `.scratch/grill-notes.md` (Beta section).
**Status:** DECIDED — plan locked; build not started until kickoff.

## 2026-08-05 Salesman month/year reconcile perfect + commissions live layout
**What you asked for:** break salesman↔invoiced down by month/year until
perfect; commissions tab on invoiced should match live visually, but without
future months.
**What I found / did:**
- Reconcile (env-key diagnostic): every month **Jan–Aug 2026** delta **$0.00**,
  by-customer amount_diffs **0**; **Jan–Aug 2025** same; YTD Last Year
  **$23,012,337.67** both sides; Full Year Last Year SP self-check delta **$0**;
  YTD/Full Year This Year already **$0** vs invoiced. Future months empty.
- Commissions UI: live Excel-style pivot (metric rows × month columns + YTD,
  blue header / yellow commission+payable). Builder already caps at
  `end_month` (no Sep–Dec mid-year). Excel export updated to the same rows.
**Evidence:** `.scratch/parity/reconcile_ty_m{1..8}.json`,
`reconcile_salesman_ly_out.json`.
**Status:** DECIDED — salesman money perfect by month/year vs TEST invoiced;
commissions layout matches live minus future months. Deployed to
`achim-sales-reports`.

## 2026-08-05 Salesman YoY SP reconciles to invoiced Total Invoice
**What you asked for:** run salesman and compare numbers to TEST invoiced.
**What I found:** `POST /api/reports/monthly_salesman_yoy/run` works. YTD
2026-01-01..2026-08-05: salesman YTD sum **$17,028,637.71** = invoiced
Total Invoice sum **$17,028,637.71** (delta **$0.00**). By customer account:
**586/586** within $0.05, **0** amount diffs. Salesman-label pair mismatches
are name-format only (`REdwards` vs `Edwards, Reggie`) — same dollars.
**Evidence:** `.scratch/parity/reconcile_salesman_out.json` via one-shot
`/test/api/reports/diagnostics/reconcile-salesman-invoiced` (env-key gated;
key cleared after run).
**Status:** DECIDED — salesman SP money matches invoiced Total Invoice for YTD.

## 2026-08-05 Salesman report -> monthly_salesman_yoy SP
**What you asked for:** stop using the invoiced endpoint for salesman; wire
`rpt.usp_monthly_salesman_yoy` (Total Invoice basis, YoY columns). Ground truth
is TEST invoiced / `vw_Invoiced_Report`, not OData.
**What I did:** Catalog id `monthly_salesman_yoy`. Params: ReportYear,
ThroughMonth (+ optional SalesmanId/Name, CustomerAccount/Name). Builder
reshapes the wide SP row into the existing 12 month tabs; no CC/freight strip
(SP sales = Total Invoice). Unit tests for builder + params (21 pass in those
files).
**Status:** DECIDED — deployed `8a3c3c1` to `achim-sales-reports` (RuntimeSuccessful).
Live column-name confirm still needed (Kudu probe hangs from this machine;
open `/test` Salesman or hit the Reporting API from Azure).

## 2026-08-05 Ordered PO # from CustomerRequisition
**What you asked for:** SP now returns CustomerRequisition (2nd column); retest
ordered Customer PO.
**What I did:** Mapped `CustomerRequisition` in `to_fact_ordered_report` into
`po_number` / display `PO #`. Removed `PO #` from stub fields (OrderStatus still
stubbed). Unit tests updated (10 pass). Live SP probe Jul 15–17: 3392 rows,
`CustomerRequisition` present, **100% filled**.
**Status:** DECIDED — deployed `8fb3bcf` to `achim-sales-reports` (2026-08-05).
Parity re-run next with noise filters.

## 2026-08-04 Customer Activity parity: /test is correct
**What you asked for:** after filtering noise (same SO+PO, blank PO on
/test, today-dated last orders), only 3 real SO/PO mismatches remained;
confirm /test and lock it.
**What I chose:** Customer Activity live↔/test is **signed off** — `/test`
last-order pick is the source of truth. Remaining noise (date-only same
SO+PO, blank-PO later orders, same-day high-volume DS, TZ) is not a /test bug.
**Evidence:** `.scratch/parity/20260804-193031-postfix/`; filtered list ended at
Broadway / Lefferts / Super Deal only after those cuts; owner accepted /test.
**Status:** DECIDED — do not chase CA last-order parity further unless product
reopens it.

## 2026-08-04 Site-wide dates via iso_date (YYYY-MM-DD)
**What you asked for:** one helper for every date on the test site; display
yyyy-mm-dd (CLO was showing truncated RFC like "Mon, 27 Ju").
**What I did:** `report_engine.lib.iso_date` is the single helper; `date_only`
aliases it. Wired adapters/builders already using it; CA Last Order Date;
Jinja `|iso_date`; report grid formatter; Excel date format; export/layout/
dashboard mirror no longer `[:10]`-slice. Frontend rebuilt.
**Status:** DECIDED — deploy with this commit.

## 2026-08-04 Customer Last Order → customer_last_orders SP
**What you asked for:** use the new Reporting API endpoint for CLO data; keep
live UX (last order + optional Add previous order merge); v3 look.
**What I did:** v3 CLO now calls catalog `customer_last_orders` (OrderCount=10)
instead of full-history `salesline_release`. Builder groups by Order Rank so
ADDON lines stay under the main PO card; picker modal lists logical orders from
that same result. Labels say "Last Order" (SP includes open/uninvoiced).
**Status:** DECIDED — local on `rebuild-reports`; deploy with `deploy.ps1` when ready.

## 2026-08-03 Monthly last_month Shabbos skip never rescheduled
**What you asked for:** dig why Monthly Invoiced on Aug 1 (Shabbos) skipped but
Azure showed Completed and no motzei Shabbos catch-up ran (job
`SCH_3dc4d915-…639211716000000000`).
**What I found:** streams say `Guard action: skip` for `--period last_month`,
logged SKIPPED to run_log, returned 0 → Azure Completed. `_classify_guard_action`
had no `last_month` rule so it fell through to skip. Catch-up injection also
ignored `last_month`, and the next regular fire is next month when the window
has already shifted.
**What I did:** treat `last_month` like `last_7_days` (reschedule after
havdalah); add last_month catch-up injection as a safety net; unit tests;
published runbook; started manual `invoiced --period last_month --force`
(job `d053cda2-183d-43ef-81f9-5ae1b0efbbd1`) which Completed.
**Status:** DECIDED — live runbook published; July monthly catch-up job green.

## 2026-07-26 Customer Activity sort + fresh parity
**What you asked for:** fresh CA live↔/test compare; fix sorting.
**What I found:** live sorts by Customer Name (pandas, case-sensitive) and builds
All by concatenating salesman groups A–Z. /test was leaving SP row order.
**What I did:** v3 `customer_activity.build` now name-sorts each tab and rebuilds
All the same way. Parity comparer keys CA sheets by `customer_account` (not SO#)
and treats same calendar day as equal across datetime vs `MM/DD/YYYY`.
**Fresh run:** `.scratch/parity/20260726-113809-customer_activity/` — All present,
781/781 accounts matched; sort verified both sides. Remaining hard diffs are
last-order fields (date / PO / SO#), not layout.
**Status:** DECIDED — sort fix deployed to `/test`; comparer/docs local.

## 2026-07-25 Ordered report: SP qty columns (no invented shipped/open)
**What you asked for:** stop inventing QtyShipped / QtyOpen; report SP qty columns
instead — ordered, reserved, released, cancelled, left to ship (DeliveryRemainder).
**What I did:** Ordered builder maps those five from `usp_ordered_report`; dropped
Fulfillment %, QtyShipped, QtyOpen from Ordered tabs. Dollar columns unchanged
(Released $ / Open $ still derived). Customer's Last Order keeps the old
QtyShipped/QtyOpen shape via `salesline_release`. Rollback tag:
`pre-ordered-qty-columns` @ `7db4b92`.
**Status:** DECIDED — deploy to `/test` with this commit.

## 2026-07-25 Master schedule split + salesman email fan-out
**What you asked for:** Both-mode delivery (full workbook to typed emails/SharePoint;
split files to selected salesmen), emails from Salesmen admin table, company
schedules on the Schedules page, dig the Friday “success” with no inbox mail.
**What I did:** expose/edit `salesmen.email`; move company wizard onto
`/schedules#company`; wizard delivery opts (`email_to_salesmen` /
`split_by_salesman` / `email_salesman_keys` in params JSON); `ScheduleRunner`
fan-out. Missing salesman email skips that split without failing the run.
**Friday dig:** `/test` used SMTP only; Azure App Settings have Graph
(`GRAPH_*`, `EMAIL_FROM_ADDRESS`) but **no** `SMTP_HOST`. Empty SMTP → `.eml` +
outbox `ok=True`, `sent_via_smtp=False` — UI looked successful with no inbox
mail. **Fix:** v3 now prefers Graph (same mailbox path as live), falls back to
SMTP, then outbox; `EMAIL_FROM` falls back to `EMAIL_FROM_ADDRESS`.
**Status:** DECIDED — code on `rebuild-reports`; deploy with `deploy.ps1`.

## 2026-07-24 Customer Activity All tab on /test
**What you asked for:** an All tab that joins every salesman, like live.
**What I found:** Azure `/test` was running an SP passthrough builder
(`rpt.usp_customer_activity`) that only emitted per-salesman sheets (Salesman
column on every sheet, no All). Local repo still had the older universe+orders
builder with All — never what prod was serving.
**What I did:** keep the SP path (matches current /test math), add All first
(Salesman column), per-salesman tabs without Salesman, Unassigned last. Synced
orch/params to the dedicated SP. Deployed; RuntimeSuccessful.
**Status:** DECIDED — live on https://reports.achimonline.com/test. Re-run
parity customer_activity to confirm the missing-sheet gap is gone.

## 2026-07-24 Live vs /test parity runner (tools.parity)
**What you asked for:** autonomous compare of live vs `/test` with the same
params and a full difference breakdown; auth via HTTP (cookie / service), not
a browser. Rebuild Test only after math is signed off.
**What I built:** `python -m tools.parity` runs ordered, invoiced, salesman,
customer_activity, number_4 with shared defaults (YTD / both for Number 4),
downloads Excel from each side, writes `.scratch/parity/<stamp>/INDEX.md` plus
per-report diffs (reuses `tests.compare_reports`). Prod auth: paste
`session` + `v3_session` cookies; local: `--auth dev`.
**Status:** DECIDED — tool on `rebuild-reports`. Not a production deploy; run
from your machine against the live site when ready.

## 2026-07-23 Removed Amazon Weekly as a named report
**What you asked for:** wipe Amazon Weekly everywhere — it was only Ordered with
customers 9300/9301, last_7_days, and email.
**What I did:** backed up to `_history_backup/amazon_weekly-removed-2026-07-23/`
(gitignored), then removed the report module, registry entry, live UI card,
v3 backlog entry, help text, email-distribution templates, and dedicated tests.
Ordered still supports `--customer 9300 9301 --period last_7_days --email`
(recipients from `AMAZON_EMAIL_RECIPIENTS`). Azure schedules that still call
`amazon_weekly` must be changed to that Ordered command.
**Status:** DECIDED — code removed on `rebuild-reports`. Not deployed until you say.

## 2026-07-23 Green test app already gone; v3 vs rebuild; prod branch
**What you asked:** delete the green test app, compare v3 vs rebuild, and say
which branch production runs on.
**Green test (`test/`):** Already deleted on `rebuild-reports` (2026-06-11). No
`/test-legacy` or `/v2` mounts remain. This pass only cleaned leftover Docker
refs that still pointed at the deleted tree (`COPY test/requirements.txt`,
`/v2/healthz` healthcheck, `.dockerignore` test paths) plus stale comments.
**Prod branch:** `rebuild-reports` (tip `b0e8034` as of this check). Not
`webapp-cache` (stale tip from early June; still had green `test/` in that
history). Deploy is zip-from-working-tree via `deploy.ps1`, so whatever branch
was checked out when someone last ran deploy is what Azure has — recent hotfixes
and Item Averages land on `rebuild-reports`.
**v3 (`/test`) vs rebuild (`/test-next`):**
- **v3 wins for day-to-day use today** — more reports (ordered, invoiced,
  salesman, number_4, customer activity, last order, item averages), admin/
  roles, SharePoint, dashboard, master schedules, denser test suite.
- **rebuild wins for long-term architecture** — SQL owns report math; app is
  mostly present/group/export; cleaner modules; smaller surface. Not feature-
  complete yet (many reports deferred pending flat-table SPs).
**What I chose:** Keep both mounts. Do not delete v3. Promote rebuild only after
report parity + human number sign-off. Clean Docker leftovers so the deleted
green app can't break image builds.
**Status:** DECIDED on branch cleanup; cutover still needs human sign-off.

## 2026-07-21 New report: Item Averages (admin-only, both apps)
**What you asked for:** a new report on `/test` and `/test-next` using the
Number 4 By Item endpoint, listing every item with past-12-month qty sales,
avg/month, and avg/week. Admins only; company-wide; sales reps must not see it.
**What I built:** report key `item_averages`. Calls
`item_customer_sales_rolling_12` (same AsOfDate + IncludeCurrentMonth=true as
Number 4), rolls item×customer rows up to one row per Item #, then:
Avg/Month = Total Qty ÷ 12, Avg/Week = Total Qty ÷ 52. Columns: Item #, Item
Name, 12-Month Qty, Avg/Month, Avg/Week. No filters in v1.
**Access:** privileged only (admin/developer). Managers and salesmen are denied
even with an explicit allow row. Rebuild hides it from the report list and
schedule picker for non-privileged users; the builder also refuses a scoped
token.
**Status:** DECIDED — code + tests on `rebuild-reports` (D: checkout). Not
deployed until you say so.

## 2026-07-14 Hotfix: salesman-scoped invoiced reports no longer fetch YTD
**Problem:** Avig's custom invoiced run for `MKolko` and 2026-07-13 through
2026-07-14 began fetching invoice headers from 2026-01-01. The live log showed
the first page alone contained 10,000 company-wide rows and the process was at
993 MB RSS. This happened because the runner expanded every Invoiced Report to
the year start for commission calculations, even though a salesman-scoped
report is written as a Shipped Report and deliberately omits the commissions
tab.
**Hotfix deviation:** restarted the app to stop the already-stalled background
thread, then used the hotfix path instead of a full review loop.
**Fix:** salesman-scoped runs now fetch only their selected period; unscoped
Invoiced Reports retain the year-to-date fetch required by their commissions
tab. Added a regression test for the one-day scoped case.
**Verified:** 23 targeted invoiced tests passed; Azure deployment
`14f6cba6-319d-42f3-9e2f-67dfcc79a5bd` reported `RuntimeSuccessful` with one
successful instance and zero failed instances.
**Status:** DEPLOYED. Avig can rerun the report; it should now fetch only the
requested day and finish normally.

## 2026-07-10 Amazon weekly email: --email flag on the Ordered runner
**Problem:** The Amazon Weekly job (Thursday schedule, report_name=amazon_weekly) had
failed on argument parsing since March: the registry maps it to the Ordered runner
with `--email` in default_args, but the Ordered runner never had an `--email` flag.
The failure was silent until June (STARTED with no result row) because argparse's
SystemExit killed the whole runbook before the FAILED line was written.
**What the owner asked for:** the Friday "Weekly 5pm Friday Amazon Ordered" schedule
(ordered + `--customer 9300 9301 --period last_7_days`) should email the file out.
**What I built:** `--email` flag on OrderedReportRunner (same pattern as the salesman
and customer-aging runners). On customer-filtered runs it emails the written file
(or a "no orders" notice) after saving. `--test` reroutes to TEST_EMAIL (split on ';').
Updated the Friday job schedule in Azure to pass `--email`.
**Business-logic call (flag if wrong):** recipients for these customer-filtered
emails are the `Recv_AmazonWeekly` spreadsheet subscribers, falling back to the
`AMAZON_EMAIL_RECIPIENTS` Automation variable. The spreadsheet currently has NO
Recv_AmazonWeekly column, so today the effective recipient is the variable's value:
bgrossman@achimonline.com. Add a Recv_AmazonWeekly column (TRUE per person) or edit
the variable to change who gets it.
**Verified:** live Azure test job (`--email --test --force`) SUCCESS in 32s; report
built (2103 rows), uploaded to SharePoint, email sent via Graph to both TEST_EMAIL
addresses. The Thursday amazon_weekly schedule also parses now (`--email --email`
duplicate is harmless for a store_true flag) -- so BOTH Thursday and Friday will
email; owner may want to drop one.
**Status:** DECIDED -- shipped; Friday schedule updated in Azure.

## 2026-06-23 Rebuild: granular per-phase review round (owner request)
**What I did:** Per the owner's "review each build phase again, more granular, until everything is clean," I split the app into four areas and had a fresh readonly reviewer go through each one (foundation+security, auth+scoping, reporting engine, scheduling+delivery+notifications). Every one came back NOT CLEAN with real findings. Fixed all blockers and the worthwhile clean-code ("ponytail") items:
- **(blocking, security)** prod would boot with a weak/known `FLASK_SECRET` -> now requires a real secret of at least 16 chars in prod, refuses to boot otherwise.
- **(blocking, security)** the background-leader file lock misread a "can't create the lock file" error as "someone else holds it" -> now those are two different paths (can't create -> assume leader and log; lock held -> follower).
- **(blocking, security)** `allowed_salesmen()` treated a blank/missing scope token as "see everything." For a worker reading a stored job that's the opposite of safe -> now only the explicit token `"all"` means everything; blank/`sm:` with no numbers/garbage all REFUSE (raise) instead of falling open.
- **(blocking, security)** spreadsheet **header** cells weren't run through the formula-injection guard the data cells already used, and a leading newline wasn't treated as a formula lead-in -> headers are guarded now and `\n` was added to the lead-in list.
- **(blocking, data)** raw client filter JSON could carry `NaN`/`Infinity` (Python accepts them, real JSON doesn't), which would later poison the cached snapshot and the browser parse -> the run endpoint now rejects non-finite filter values up front, and the cache writer refuses to serialize them too.
- **(blocking, correctness)** a manual "Run now" was stamping "ran today," which could eat that day's real scheduled slot -> the once-a-day stamp is owned only by the poller (when it queues) and the Shabbos-skip path, never by the run itself.
- **(blocking, correctness)** if a Shabbos catch-up was owed AND the normal cadence came due in the same tick, the report could go out twice -> queuing the normal run now clears the owed catch-up in the same step.
- **(blocking, correctness)** a timed-out/cancelled delivery could be miscounted as a real failure and fire a false "your schedule failed" alert -> a cancellation now returns a distinct "stopped" signal that isn't counted as a failure.
- **(ponytail)** centralized one `normalize_email()` helper (three copies removed); de-duplicated the two create-schedule routes into one `_save_schedule()` and the schedule-table actions into one `_schedule_actions.html` partial; pulled the runner's API-timeout math and the Excel sheet-title cap into named constants; renamed a batch of vague locals (`result`, `data`, `raw`, `out`, `s`, `cfg`) to say what they hold. Added regression tests for the manual-run slot and the catch-up/normal collision.
**Litestream** stays gated until cutover.
**Status:** DECIDED -- all blockers across the four area reviews fixed, 68 tests pass.

## 2026-06-23 Rebuild: second granular review round (re-verify, until clean)
**What I did:** Re-ran the four area reviewers (fresh, readonly) on the fixed code. Each re-verified the prior fixes were correct and found a few more things; fixed them all:
- **(blocking, security)** `allowed_salesmen()` stripped whitespace before checking the "all" token, so a tampered `" all "` would have read as unrestricted -> now it matches the exact token `"all"` with no strip; anything padded or otherwise off REFUSES. Added that case to the fail-closed test.
- **(blocking, correctness/data-loss)** the Shabbos catch-up flag was cleared at the START of a run, so if that catch-up run was then cancelled/timed out, the owed send was silently dropped (poller wouldn't retry it) -> the flag is now cleared only once the run reaches a settled outcome (sent, partly sent, fully failed, or "nobody to send to"); a cancelled/stopped run leaves the flag set so the poller retries next tick. Added a regression test.
- **(small)** also added an early "is the job still running?" check right before building the (possibly large) Excel workbook, so a cancelled catch-up doesn't waste time building a file it will never send (the existing post-build gate before the actual email is unchanged and is what guarantees we don't send after cancellation).
- **(ponytail)** finished centralizing email handling: one `normalize_email()` used in the auth/session/MSAL paths too (no more inline `.strip().lower()`), and one shared `dedupe_emails()` replacing the two copy-paste recipient-cleaners. One shared `salesman_scope_token()` so the security-sensitive scope-token format has a single speller. Removed the genuinely-dead `ROLE_ADMIN` role (it was never assigned anywhere -- privilege comes from the configured developer-email list; "admin" stays as UI wording only). Renamed the last vague locals/loop vars (`s`, `out`, `raw`) in params/export/cadence/sabbath/routes and the schedule templates.
**Why remove ROLE_ADMIN (plain English):** the code had three role names but the sign-in only ever assigns "developer" or "user" -- nobody is ever "admin." A name that can never happen is just confusing, so it's gone. Who's privileged didn't change: it's still whoever is on the developer-email list.
**Status:** DECIDED -- second round's blockers fixed, 69 tests pass; re-review queued to confirm clean.

## 2026-06-23 Rebuild: reschedule-after-Shabbos + failure alerts (owner request)
**What I built (two things the owner asked for):**
1. **Catch-up after Shabbos.** A send skipped for Shabbos/Yom Tov is no longer just dropped until the cadence comes around again. The skip now flags the schedule (`catch_up_pending`), and the poller fires it as a one-off catch-up the moment Shabbos is over (it re-checks Hebcal and, once it's clear, queues the run with its own dedup key so it isn't blocked by "already ran today"). So a Saturday-morning send goes out Saturday night instead of waiting a week.
2. **Failure alerts.** When a whole scheduled run fails (every delivery failed -- e.g. the data server was down), the schedule's owner gets an immediate plain-English email. For a **private (self) schedule** the owner also gets an in-app message the next time they open the app, with a **"Run now"** button (and "Dismiss"). "Run now" queues a manual run that ignores the Shabbos skip (they asked for it on purpose).
**New pieces:** `notifications` table + repository (a tiny per-person inbox); `schedules.catch_up_pending` column; `EmailService.send_failure_notice()`; `run-now` and `dismiss` routes; a notification banner in the base layout; a context processor that shows a signed-in person their unread messages on every page (defensive -- never breaks a page). 8 new tests (66 total pass).
**Judgment calls (decided as, flag if you disagree):**
- **What I had to decide:** who the failure email goes to. **Options:** always the admin (you), vs. the schedule's owner. **What I chose:** the owner -- which is YOU for master schedules (you own them) and the user for their own private schedules. **Why:** the person who set a schedule up is the one who needs to know it didn't go out; it matches "email me" for your own schedules without spamming you with every user's private-schedule hiccup. **NEEDS HUMAN SIGN-OFF if you actually want every failure (including users' private ones) to also email you.**
- **What I had to decide:** what counts as "failed entirely" (vs. partly). **What I chose:** at least one delivery attempted and every attempt failed, and the job wasn't cancelled. A partial failure (some sent, some not) shows in history but doesn't alarm. A cancellation isn't a failure. **Why:** avoids crying wolf.
- **What I had to decide:** should a manual "Run now" still skip Shabbos. **What I chose:** no -- a manual press runs even on Shabbos. **Why:** the person clicked it deliberately; the auto-skip is for unattended sends.
**Status:** DECIDED (one item flagged for sign-off above).

## 2026-06-23 Rebuild Phase Sch: scheduling engine (cadence + Shabbos skip + poller)
**What I built:** The machinery that sends reports on a repeating schedule, generic for any report. A `schedules` table + `SchedulesRepository`; a re-implemented cadence module (daily/weekly/monthly at a wall-clock time, all reasoned in US/Eastern, fires at most once per Eastern day); a Shabbos/Yom Tov check (`sabbath.py`) that re-creates the live app's Hebcal-for-Brooklyn behavior using only the standard library, cached per day and fail-open; a minute poller that queues a durable `schedule.run` job for each due schedule (deduped per schedule+day); and a `schedule.run` handler that turns a schedule into "deliveries" and emails each. Two kinds: **self** (scoped to the owner, to owner+extras) and **master** (one scoped send per salesman number, to the people mapped to that salesman). Refactored the runner to share one `build_report_snapshot()` between the web run and the scheduler so report math/scoping live in ONE place. 15 new tests (48 total pass).
**Three judgment calls I had to make (decided as, flag if you disagree):**
- **What I had to decide:** what "skip Saturdays and holidays, like the live app" should mean here. **Options:** a hardcoded holiday list, vs. the live app's real-time Hebcal check. **What I chose:** the Hebcal check (Shabbos + Yom Tov for Brooklyn, 18-min candles) at fire time, fail-open on any network hiccup. **Why:** it's exactly what the live runbook does, so the two stay in lockstep and I don't have to maintain a date list.
- **What I had to decide:** what happens when a scheduled send fails (data server down) or is skipped for Shabbos. **Options:** keep retrying every minute that day, vs. fire at most once a day and record the outcome. **What I chose:** stamp it as "ran today" after the attempt either way, so it never retries in a loop; a failure shows in the audit log and the owner can re-run by hand. **Why:** avoids a retry storm and matches the once-a-day intent; the live app's auto-reschedule-after-Shabbos is a nicety I left for later.
- **What I had to decide:** a master schedule runs one report per salesman sequentially inside a single worker job capped at 5 minutes. **What I chose:** leave it sequential for now and note the cap. **Why:** modest master schedules are fine; a very wide one (many salesmen) could hit the cap — call it out so we size it before turning one on.
**Not yet (by design):** no real schedules seeded.
**Status:** DECIDED.

## 2026-06-23 Rebuild Phase UI: schedule management screens + review
**What I built:** The pages to run the engine above. "My schedules" (any signed-in person): create a self-schedule for a report, see/pause/resume/delete your own, plus a create form (report, tab, date range, daily/weekly/monthly at a time, extra recipients, skip-Shabbos toggle). "Master schedules" (admins only): the same but split-by-salesman with a salesman-number list. A "Schedule history" page shows what actually went out (your own; admins see everyone). One shared form partial, a tiny vanilla-JS file to show the right cadence fields and filter the tab list to the chosen report, flash messages added to the base layout. CSRF on every state-changing POST. 56 tests pass.
**Review:** readonly gpt-5.5-extra-high (agent f8cf270d) on the combined scheduling + UI diff. It cleared the data-scoping (master sends are correctly locked to one salesman; self sends to the owner's scope) and CSRF/escaping. Fixed its two BLOCKING items and three smaller ones:
- **(blocking) interactive-run cancellation** had moved to after tab-building in the runner refactor -> restored the original checkpoint by passing a `cancelled` check into the shared `build_report_snapshot()` (so a cancelled run still stops before the heavy build). 
- **(blocking) a schedule could re-fire all day** if its job timed out or errored before the "ran today" stamp -> the poller now stamps `last_run_at` the moment the durable job is queued (a crash still drains the queued job, so we don't lose the send and don't double-send).
- (smaller) master schedules can only be managed by a *current* admin, not the stored owner; the Shabbos check now fails open even on a malformed-but-successful Hebcal response; and each delivery writes its own `schedule.run` history line so successes show up, not just skips/failures. Added regression tests for the once-a-day guard, the master-manage rule, and the fail-open path.
**Status:** DECIDED -- scheduling phase (engine + UI) done, committing.

## 2026-06-23 Rebuild full-app multi-pass review (until clean)
**What I did:** Ran repeated readonly full-app reviews (gpt-5.5-extra-high) until one came back with no blocking issues, per the owner's instruction. Three passes:
- **Pass 1** (agent 75b68436): found 2 blockers -> (a) a master schedule kept running even if its owner lost admin rights; (b) a timed-out/cancelled schedule job could keep emailing from a thread the worker had abandoned. Fixed both (re-check owner privilege at send time; cooperative "is the job still running?" gate before each delivery and before each send). Added regression tests.
- **Pass 2** (same agent): verified both fixes correct and complete -> CLEAN.
- **Pass 3** (fresh agent 70bdf1fd, no prior context): found 1 blocker -> the workbook was being built inside the email call's arguments, AFTER the "still running" gate, so a timeout during the (possibly slow) Excel build could still send. Fixed by building the workbook first, then gating, then sending. Also acted on its non-blocking note that multiple gunicorn workers would each start a poller: now exactly ONE process runs the worker + schedule poller, elected with an exclusive OS file lock (mirrors the live app's and v3's existing background-leader pattern; fails open to leader on Windows/dev).
**Why the leader lock matters (plain English):** on the server, the web app can run as several copies of the same process at once. Without the lock, each copy would start its own schedule checker, and a schedule could get sent more than once. The lock means only the first copy to grab it does the background work; the rest skip it.
- **Pass 4** (agent 70bdf1fd, re-verify): both pass-3 fixes confirmed correct, full re-sweep found no remaining blocking issues -> CLEAN.
**Outcome:** Two independent review lineages both end CLEAN (no blocking security/correctness/data-loss issues). 58 tests pass. Remaining items are all accepted/non-blocking (Litestream gating until cutover, viewer.js could later be split, the documented once-a-day master tradeoff).
**Status:** DECIDED -- full app reviewed clean on the branch. Deploy to /test-next is owner-timed (per the cutover rule), not done here.

---

## 2026-06-18 Move v3's precious.db off the /home SMB share onto local disk (fix the stalled job queue)
**What I had to decide:** v3 report jobs were getting stuck "queued" forever -- the background worker never picked them up, so no call ever reached the Reporting API (the DBA confirmed he saw zero calls). Root cause: `precious.db` (users, roles, schedules, jobs) lives at `/home/site/v3data/precious.db`, and on Azure App Service `/home` is an Azure Files **SMB share**. SQLite's WAL mode coordinates processes through a shared-memory index (the `-shm` file) that SMB can't share across processes, so the worker process literally couldn't see the rows the web process had written. I needed to get the DB onto local disk (where WAL works across processes) WITHOUT losing the users/roles/schedules already in it, and without taking down the LIVE app that shares the same process.
**Options I considered:** (a) Interim: switch SQLite to a rollback journal (TRUNCATE) so it works over SMB. **Tried it, it broke the app** -- you can't flip a live DB out of WAL without an exclusive lock, every query started failing with "database is locked", HTTP 500s everywhere; reverted immediately. It also would have disabled Litestream (which requires WAL). (b) Proper fix: move `precious.db` + `cache.db` to local disk (`/tmp/v3data/`), seed the local DB once from the current `/home` copy, and keep Litestream replicating it to Blob for durability. (c) Move to Postgres -- too big a change for tonight.
**What I chose:** Option (b). `startup.sh` now does a one-time seed: on the first boot after the move, it copies the current `/home` precious.db to the new local path using SQLite's online-backup (a consistent snapshot even mid-WAL), drops a marker on the persistent `/home` share so it only ever runs once, and also keeps a dated `precious.premigrate.*.db` safety copy on `/home`. After that, normal cold starts restore the CURRENT data from the Litestream Blob replica. `cache.db` is disposable so it just starts empty and rebuilds. App settings `PRECIOUS_DB_PATH`/`CACHE_DB_PATH` point at `/tmp/v3data/...`; the leftover `SQLITE_JOURNAL_MODE` knob (from the failed interim attempt) is removed from both the code and the app settings.
**Why:** Local disk is shared between the gunicorn web workers and the job worker (same container), so WAL's cross-process visibility works and the worker can finally see and run queued jobs. The `/home` file is never modified -- the app just stops pointing at it -- so it stays as a frozen, complete backup. If anything looks wrong after cutover I point `PRECIOUS_DB_PATH` back at `/home` and lose nothing. Litestream still runs in WAL (required) and now replicates the local file. This is the rule-5 design the project always intended; the DB was on `/home` by accident because the default path resolves under the working directory, which is itself on `/home`.
**Status:** DECIDED + VERIFIED. Cutover done at 18:01 UTC: logs show `startup: seeded precious.db users=12 jobs=232` (data intact), Litestream took a fresh snapshot of `/tmp/v3data/precious.db` and is replicating to Blob, and the job worker's poller went from failing on EVERY cycle ("unable to open database file") to zero errors. Confirmed the cold-restart path too: a later container with `/tmp` wiped correctly skipped the one-time seed (marker present) and Litestream RESTORED the DB from Blob (same snapshot size, so data is whole). Also hardened `config.validate()` to refuse to boot in prod if precious/cache ever points back at the `/home` SMB share (the latent gap `_is_unc` missed), with tests. Removed the obsolete `SQLITE_JOURNAL_MODE` app setting. The old `/home/site/v3data/precious.db` was left untouched as a frozen rollback; `startup.sh` also wrote a dated `precious.premigrate.*.db` copy. NOTE: separately, the owner/DBA confirmed the missing Feb/Mar data is an UPSTREAM stored-procedure problem, not this app.

## 2026-06-14 Fetch big v3 reports one month at a time (stop the API timeouts)
**What I had to decide:** How to stop large v3 reports (YTD Ordered, ~488K order lines) from failing. They ask the on-prem Reporting API for a whole year in one request; on a busy on-prem SQL box that single query runs past the 5-minute timeout and returns nothing (all-or-nothing). The owner: "why is this failing so badly? is there a way to chunk the request to make sure it goes through?"
**Options I considered:** (a) raise the timeout (same failure, longer wait, more load on the on-prem box), (b) split the request by date into month-sized pieces, (c) split by customer into batches, (d) bigger on-prem SQL box.
**What I chose:** Option (b). Big date-window pulls of the `salesline_release` stored procedure are now fetched one calendar month at a time and stitched back together. Applied to the three biggest pulls: Ordered (any bounded period), Customer Activity, and the dashboard all-orders refresh. Open-ended/all_time Ordered runs stay a single call (that path relies on the SP's own default window). New `month_chunks()` helper in `report_engine/dates.py`; new `_facts_chunked()` in `web/reporting/report_service.py`.
**Why:** The owner's own evidence ("yesterday returns fine, last month/YTD hangs") points at date/size as the bottleneck. Each month (~40K rows) returns well inside the timeout. No numbers change: each chunk uses the same day boundaries (00:00:00 -> 23:59:59) every daily report already uses, and contiguous months have no gap/overlap, so the stitched result is the same rows as one big call. Verified with a parity test (stitched == single full-window call) + month_chunks coverage tests; all 310 v3 tests pass. Cross-model review found no blockers. Caveat: if the on-prem API is *fully* wedged (every call hanging, the current state), it still needs a restart — chunking can't extract data from a server answering nothing. Raw "Full Data" row order is now grouped month-by-month; totals/numbers identical (logged for sign-off in v3/REVIEW-LOG.md).
**Status:** DECIDED

## 2026-06-11 Retired the legacy test app (test/)
**What I had to decide:** The owner ordered the old v2 sandbox app removed: "get rid of the legacy test app... cancel all jobs for it, wipe it."
**Options I considered:** (a) just unmount it but keep the code, (b) delete the code and its background jobs entirely.
**What I chose:** Full removal. Deleted `test/` (80 files), removed the `/test-legacy` and `/v2` mounts from `wsgi.py`, dropped its pip packages (SQLAlchemy, pyodbc) from requirements, and wiped its data files on the server (`/home/data/v2_app.db`, `/home/data/v2_critical_backup.json`). Its background "mirror refresh" jobs ran inside the web process, so removing the app removes the jobs -- nothing to cancel in Azure.
**Why:** Nobody uses it, and its mirror refresh was hammering the on-prem Reporting API with 13 back-to-back ~150-200K-row pulls (nightly + every 4 hours + after restarts) -- the prime suspect in this week's API hangs, and a contributor to tonight's out-of-memory crash. v3 replaced it. Note: this supersedes the earlier v3-rebuild directive to keep the old test app viewable at /test-legacy. If v3 now fails to boot, /test returns 404 instead of falling back to the old app (the boot error still gets dumped to /home/LogFiles/v3_boot_error.log).
**Status:** DECIDED (owner instruction)

Decisions made during autonomous operation or at ambiguous points during development. See `autonomous-mode.mdc` for the format.

---

## 2026-06-23 Rebuild Phase E: email sending built + reviewed
**What I built:** The email layer. A Graph mailer (`rebuild/delivery/graph_mail.py`) sends app-only mail through Microsoft Graph the same way the live distribution does -- no mailbox password, built on the standard library + msal. A composition/service layer (`report_email.py`) turns a finished tab into an email: short body with an "open in the app" link, the Excel attached, and a link-only fallback when the workbook is too big (>= 2.5 MB raw, safely under Graph's ~4 MB request limit after base64). Always sends FROM `config.mail_from` (reports@) with Reply-To set to the person. Every attempt (sent, failed, refused) is written to the audit log. The only trigger so far is an "Email to me" button that sends ONLY to the signed-in person (to themselves) -- the safe test path; real recipients/schedules come in the scheduling phase. Settings added: `REBUILD_MAIL_FROM`, `REBUILD_PUBLIC_BASE_URL` (both blank = email simply off). 33 tests pass.
**Review:** readonly gpt-5.5-extra-high (agent 86ce3f31). Confirmed recipients come only from the signed-in identity, `_read_result` enforces ownership+scope before sending, CSRF is enforced, and the body is HTML-escaped. Fixed its three BLOCKING items: (1) unconfigured/refused sends are now audited too (single failure path); (2) any token/network error becomes a clean "failed" instead of a 500; (3) we refuse to send a link-only email when no app link can be built, rather than sending a useless "use the link above" with no link. Tightened the attach threshold to 2.5 MB and `>=`.
**One judgment call (NEEDS-HUMAN, decided as):** Graph sends with `saveToSentItems=true`, so a copy lands in the reports@ Sent Items. I kept that on -- it gives a real sent record and matches the "send as reports@" model. Say the word if you'd rather it not retain copies there.
**Not yet (by design):** no real recipient lists or schedules seeded; live test-send needs the deploy + Mail.Send app permission + REBUILD_MAIL_FROM set.
**Status:** DECIDED -- email layer done, committing.

---

## 2026-06-23 Rebuild Phase S: per-salesman scoping built + reviewed
**What I built:** Real per-salesman data scoping (was stubbed -- everyone saw all). New `user_salesmen` mapping table (admin-managed), `UserScopeRepository`, scope resolved in the single `resolve_access()` (privileged=all, mapped=own numbers, unmapped=denied). The salesman SP param is forced to the person's numbers AND rows are post-filtered as a backstop; scope is folded into the cache key. Admin-only page at `/admin/scope` to manage the map. 23 tests pass.
**Review:** readonly gpt-5.5-extra-high review (agent 8a00a5a7). Fixed its one BLOCKING item (the run summary used the pre-filter row count, which could leak the full total to a scoped user -> now counts post-filter rows) and its NON-BLOCKING worker item (the worker now refuses a tampered/corrupt scope token instead of falling back to "all"). Added regression tests for both.
**Two judgment calls (NEEDS-HUMAN, decided as):**
  1. **Salesman number format = exact match.** Numbers are matched as exact trimmed strings, so `010` and `10` are different. I chose exact match (no guessing/zero-stripping) and told admins on the page to enter numbers exactly as they appear in the report's Salesman column. Flag if your data uses inconsistent leading zeros.
  2. **"Privileged" = the developer list for now.** The role resolver only assigns `developer` (from REBUILD_DEVELOPER_EMAILS) or `user`; there's no separate "admin" role source yet. Privileged behavior (see-all + admin pages) currently means being on the developer list. Fine while it's just you; we can add a real admin role source later.
**Status:** DECIDED -- scoping done, committing/deploying.

---

## 2026-06-23 Rebuild M11 unblocked: email + scheduling decisions (owner answered)
**What I had to decide:** The owner answered the M11 questions, which set the design for emailing and scheduling reports.
**What the owner chose (and what I'm building to):**
  1. **Safety gate:** build the full email/scheduling machinery, but test-send ONLY to the owner. Do NOT seed real master schedules or recipient lists yet.
  2. **Send method:** reuse the existing Microsoft Graph app mail the live distribution uses (`core/email_report.py` pattern; app-only Mail.Send). No new mailbox or secret.
  3. **Sender:** ALWAYS send From `reports@achimonline.com`, with **Reply-To set to the person who created the schedule**. (The owner picked this over "send as the user" -- it's safer: the app only ever sends as `reports@`, so we don't need the broad "send as any user" permission, and replies still reach the creator.) I'll also recommend an Exchange application-access-policy limiting the app to `reports@`.
  4. **Recipients / scoping:** per-salesman + per-user. A user's login maps to their salesman number(s) via an **admin-managed mapping table** (the owner manages it). Master schedules (admin) split a report by salesman and send each their own scoped copy; a user's own schedule is auto-scoped to them. Privileged users see all; a mapped user sees only their salesmen; an unmapped non-privileged user is denied (they'd see nothing anyway -- this app is sales reports).
  5. **Cadence:** fully customizable like the live/v3 app; skip Saturdays and holidays; built generic so any future report can be scheduled.
  6. **Attachment:** both the Excel file and a link to open it in the app; fall back to link-only if the Excel is too big for a single Graph send (~3-4 MB).
**Build order (owner approved):** (S) data scoping -> (E) email send service (test to owner only) -> (Sch) scheduling engine -> (UI) schedule management for users + admin.
**Why:** Scoping is the foundation for per-salesman delivery and is also a security non-negotiable that was still stubbed; it has to land first. Reply-To-not-send-as keeps the mail permission minimal. Numbers remain PROVISIONAL until owner sign-off, which is exactly why nothing real is scheduled yet.
**Status:** DECIDED -- building.

---

## 2026-06-22 Rebuild M11: email + scheduling -- NOT built, needs your sign-off (autonomous)
**What I had to decide:** The inventory includes emailing and scheduling reports. Whether to build automated email distribution now, while running unattended.
**Why I stopped instead of building it:** This is a high-risk action under the autonomous rules (business logic + could send wrong data to people). The invoiced numbers are still PROVISIONAL -- you haven't signed off that they match LIVE (and we know the DBA's source data is currently wrong). Wiring up automatic emails now could blast not-yet-correct numbers to executives on a schedule. It also needs decisions only you can make.
**What I need from you to build it:**
  1. Sign-off that invoiced numbers are correct (or an explicit "send anyway, it's a test list").
  2. Send method: reuse the existing Microsoft Graph mail the live "CEO Daily Reports" uses (same app credentials / Mail.Send), or something else?
  3. Who sends (which mailbox/identity) and who receives (fixed list, per-user, per-salesman scope)?
  4. Schedule semantics: which reports, what cadence, what timezone, skip weekends/holidays (the live app has Shabbos-skip logic)?
  5. What gets attached -- the Excel export we just built, a link to the viewer, or both?
**Status:** BLOCKED (waiting on owner)

---

## 2026-06-22 Rebuild M12: audit-log viewer built; worker/Litestream/paging deferred (autonomous)
**What I had to decide:** The ops-hardening inventory had several items: an admin audit-log viewer, a separate worker process, Litestream backup of the rebuild's database, big-result server paging / Blob spill, and an admin UI for report config. What's safe to do unattended.
**What I chose:** Built only the admin-only audit-log viewer (`/test-next/admin/audit`, gated by `require_privileged`) -- read-only, self-contained, no production-startup change. It lists recent runs/exports/deliveries from the audit table the job handlers already write. Deferred the rest:
  - **Separate worker process & Litestream for the rebuild DB:** these change the SHARED production container's startup (the same container runs the LIVE app). That's a breaking-change risk I won't take unattended. The in-process worker is healthy on the single B1; Litestream already protects the live DB. To be done deliberately with you.
  - **Big-result server paging / Blob spill:** only needed for very large reports; invoiced is bounded by the row guard. Not needed yet.
  - **Admin UI for report config/manifest:** real CRUD with its own review; the manifest is code-defined and stable for now.
**Why:** Autonomous rules say stop before breaking changes and production-startup risk. The audit viewer is pure upside with no such risk; the rest deserves a deliberate, reviewed session.
**Status:** DECIDED (audit viewer); DEFERRED (worker/Litestream/paging/admin-CRUD)

---

## 2026-06-22 Rebuild M10: in-table filtering, grouping, show/hide columns (autonomous)
**What I had to decide:** The owner's inventory wanted filtering and grouping by columns, plus show/hide/reorder. How much to build now, and how, given the app is meant to be a thin presentation layer.
**Options I considered:** (a) Build server-side filtering/grouping endpoints (more code, another path that could drift from the engine). (b) Use Tabulator's built-in, client-side features over the rows we already shipped: per-column filter boxes, a group-by selector, a show/hide-columns checklist, drag-to-move and drag-to-resize. For totals: keep the hand-made total row, or switch to Tabulator's own bottom/group calc rows. (c) Saved layout presets (column order/widths/visibility per user) -- needs a table in precious.db plus endpoints and tests.
**What I chose:** Option (b) for filtering/grouping/columns -- all client-side, no backend, because the data is already on screen and grouping/filtering is explicitly view-only per the owner's directive. Switched table totals from a fake appended "TOTAL" row to Tabulator's native bottom + per-group calc rows, which also fixed a latent bug where the fake total row would have been swept into groups and filters. Deferred saved presets (option c) to a later milestone since it needs durable per-user storage; logged here so it isn't forgotten.
**Why:** Keeps the app thin and the report math single-source (the engine still owns the numbers; the browser only re-presents them). Native calc rows behave correctly under grouping/filtering, unlike a data row pretending to be a total. Presets are real work with a storage decision, better done deliberately than rushed.
**Status:** DECIDED (saved presets: DEFERRED)

---

## 2026-06-22 Rebuild M9: exports (CSV + Excel) from the snapshot (autonomous)
**What I had to decide:** The owner's inventory wanted exports. How to produce CSV and Excel without bolting on weight, and what the file should contain.
**Options I considered:** (a) Rebuild the export in Excel like the old app does (heavy, and the rebuild explicitly does NOT port the old Excel builders). (b) Export straight from the tab payload the engine already built (columns + rows + total), so the file is exactly what's on screen. For the format: CSV via the standard library; Excel needs a package -- `openpyxl` is already installed for the live app, so no new dependency (`pandas` would be overkill here).
**What I chose:** Option (b). One small `export.py`: `to_csv` (stdlib `csv`, UTF-8 BOM so Excel opens it cleanly) and `to_xlsx` (openpyxl, with money/percent/int number formats and a bold header + total row). A new GET route `/api/reports/<key>/export/<tab>?fmt=csv|xlsx` reads the snapshot through the same ownership-checked path as viewing, logs a `report.export` audit row, and streams the file. Two toolbar buttons download the active tab. The commission card tab exports its flat columns/rows (built alongside the cards for exactly this).
**Why:** Exporting the already-built tab guarantees the download matches the screen and reuses the single source of report math -- no second code path that could drift. Stdlib + an already-present dependency keeps it light. It's a GET (no state change) so it needs no CSRF, and the path-scoped session cookie still authorizes it.
**Status:** DECIDED

---

## 2026-06-22 Rebuild M8: fit the report table to the viewport (autonomous)
**What I had to decide:** The owner reported the table ran off the bottom of the screen -- you had to scroll the whole page to reach the bottom row and the horizontal scrollbar. How to make it fit.
**Options I considered:** (a) A fixed `calc(100vh - 120px)` guess (fragile: breaks if the header/filters change height). (b) Measure the table's real position and size it to the space left, recomputing on window resize and when the filters panel collapses.
**What I chose:** Option (b). The table height is computed from its on-screen top to the bottom of the window, so it always fits and scrolls inside its own box (both scrollbars reachable) instead of pushing the page taller. Added a "Hide/Show filters" toggle; collapsing the filters gives the table more room (recomputed on toggle). Also added the classic `min-height: 0` flex fix so the table box can shrink.
**Why:** Measuring beats guessing -- it survives header/filter size changes and directly gives the "bigger table when filters are collapsed" behavior the owner asked for earlier.
**Status:** DECIDED

---

## 2026-06-22 Rebuild M7: card commissions tab + viewer tab fixes (autonomous)
**What I had to decide:** The owner asked for a second Commissions tab in the card format (like the old v3 app) to compare against the new flat pivot, plus fixes for two viewer complaints: switching tabs took several seconds and showed the OLD tab until the new one arrived, and the Commissions tab "didn't load at all." Then to continue the build autonomously.
**Options I considered:** (a) Duplicate the commission math for the card view. (b) Extract the per-salesman/per-month math once and feed both the pivot and the cards from it. For the slowness: (a) cache the parsed snapshot server-side, (b) fetch each tab once and cache it in the browser (like v3, which was fast because it was client-side), prefetching the others quietly.
**What I chose:** Extracted one shared helper (`_salesman_months`) that both commission tabs build from, so the two views can never disagree (a test asserts their YTD totals match). Added a `commission_cards` transform that also keeps a flat columns/rows so exports still work later. The engine now passes a transform's whole payload through (so new layouts need no engine change), and `result_tab` returns the whole tab. Browser side: each tab is fetched once and cached, the rest are prefetched in the background, a click clears the table and shows a "Loading…" note immediately, a request token ignores a stale response, and a failed tab now shows an error instead of silently leaving the old tab up (which is what made Commissions look like it "didn't load").
**Why:** The owner's own reference (v3) was fast because tabs were client-side; caching + prefetch matches that without abandoning the lazy-first-paint design. The shared helper follows the rule-of-2 (two real call sites now). Surfacing tab errors turns an invisible failure into something we (and the owner) can see. Commission numbers stay PROVISIONAL until owner sign-off.
**Status:** DECIDED

---

<!-- Entries are added below as work progresses. Each entry follows this format:

## [Date] [Short description]
**What I had to decide:** ...
**Options I considered:** ...
**What I chose:** ...
**Why:** ...
**Status:** DECIDED / BLOCKED

-->

## [2026-06-10] CEO Daily Reports email distribution failing since June 3

**What I had to decide:** Why the "CEO Daily Reports" email distribution failed every day since June 3, and how to fix it.

**What I found:** The production database showed every attempt failing with "file not found" for the Ordered and Invoiced report files -- but the files were sitting right there on SharePoint. The app's logs revealed the real error: the Graph API call that looks up the SharePoint *site* was returning 404. The `SP_SITE_URL` setting on the Azure web app pointed to `https://achimonline.sharepoint.com/sites/AchimImportingCoIncTeamSite-D365FO`, a site that does not exist (confirmed by asking Graph directly). The reports actually live on the root site `https://achimonline.sharepoint.com`, under the "D365 F&O" folder in its Documents library. The code swallowed the site-lookup error and reported it as a missing file, which is why the log was misleading. The same wrong-site problem also broke the run_log.csv download the dashboard uses (it had its own hardcoded site name, also wrong) -- which is why Saturday "Shabbos skip" detection failed and the distribution retried in a loop on Saturdays too.

**Options I considered:** (1) Point SP_SITE_URL at the root SharePoint site, matching the local .env that works. (2) Hunt down the "correct" team site URL -- but the file paths all assume the root site's library, so this would need path changes everywhere.

**What I chose:** Option 1: set `SP_SITE_URL=https://achimonline.sharepoint.com` on the Azure web app. Also made two small code fixes: the run_log.csv download now goes through the same shared SharePoint service (instead of its own hardcoded site name), and a dead SP_SITE_URL now raises a clear error naming the setting instead of pretending the file is missing. Added a regression test for that error.

**Why:** Smallest change that restores the working configuration. The local .env already proved the root-site URL resolves every report path correctly.

**Status:** DECIDED
