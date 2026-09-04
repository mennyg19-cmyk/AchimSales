## 2026-09-04 Q8 is account provisioning, not pending mail approval
**What I had to decide:** Owner locked Q8: external people do not self-register. Only admin/developer can add them in People. After the email exists they magic-link in.
**What I chose:** Build that. No pending-recipient queue. Magic link must use the v3 `users` row (`is_external`, active). Home login form must not depend on live `app_users`. Keep `/legacy` magic-link as-is for the mounted Live app. Q9: view-only managers may POST company Send now; edit/delete stay `can_edit_master`. Do not unmount. Do not merge. Do not add an Azure slot.
**Why:** Owner message 2026-09-04. Azure slots left for later (needs Standard S1+).
**Status:** DECIDED — implementing
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-04 Owner retired Azure Automation as a leftover/go-live path
**What I had to decide:** Whether Phase 9.2 still requires proving Azure Automation sends every distribution.
**What I chose:** Drop that leftover. In-app company/personal schedules are the production sender. Do not verify, publish, or keep Automation as a go-live gate. Leave `runbooks/` and `deploy-runbook.ps1` in the repo unused until an explicit delete is asked. Do not unmount `/legacy` `/test` `/test-next`.
**Why:** Owner: “I dont want Azure Automation anymore, so leave that out.”
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-04 Phase 8 bounded fuller browser matrix
**What I had to decide:** Whether to combinatorial-test every Phase 8 report flow, or bound the leftover matrix to overflow and role access.
**What I chose:** Bound it. Isolated Chrome CDP: 224 allowed-page width/theme cases plus disabled-login denial, 225/225 PASS. Do not claim magic-link, report run, Keep, export, email, or Send now coverage.
**Why:** Representative 8.15 already covered live regions/tablist. Full flow×role×width×theme is not leftover hygiene.
**Status:** DECIDED
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-04 Phase 9.2 support/recovery inventory
**What I had to decide:** Whether the leftover “no old route/test/tool/doc needed” bullet can be checked without unmounting.
**What I chose:** Leave it unchecked. Keep `/legacy`, `/test`, `/test-next`, `/beta` redirect, their route tests, the universal Automation runbook/publisher, and the live-vs-`/test` parity diagnostic. Do not delete historical `GO-LIVE-DAY-REPORT.md` / `rebuild/REBUILD-PLAN.md` / retired `test/` in this leftover. Azure send-verify stays owner/ops.
**Why:** Phase 7 still forbids unmount. Q6 retired in-app distributions as product, not as mounted `/legacy` code.
**Status:** DECIDED (inventory). Bullet stays open until mounts can drop.
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-04 Phase 9.1 totals/export/role-scope code compare
**What I had to decide:** Whether archive-vs-v3 footer and schedule-fanout differences are bugs, and whether frozen goldens can be invented.
**What I chose:** Record Customer Activity count footer and Salesman percent-footer as unknown. Keep the three earlier semantic unknowns. Invoiced explicit-zero commission stays Q2. Do not invent XLSX goldens; owner samples are required. Schedule management-vs-salesman fanout is an implementation change, not delivery proof.
**Why:** No in-repo workbook fixtures in either worktree. Spec gate forbids picking product meaning from code shape.
**Status:** DECIDED (code-level 9.1 done). Value goldens BLOCKED on owner samples.
**Model:** gpt-5.6-terra-medium
**Runner:** spawn

## 2026-09-04 Phase 9.1 tab/column code compare
**What I had to decide:** Whether three archive-vs-v3 column/scope differences are bugs.
**What I chose:** Record them as unknown. Do not pick a product meaning. Ordered shipping/remainder fields, Number 4 By Item dollars, and Last Order invoiced-vs-open scope wait for goldens or owner. Invoiced explicit-zero commission rate is Q2 (intentional-diff). Four reports match at tab/column source.
**Why:** Spec gate: no signed sample workbooks in this leftover.
**Status:** DECIDED (inventory + code compare). Remaining 9.1 goldens still open.
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-04 Phase 9.1 inventory does not use live cookies
**What I had to decide:** How to start archive report parity without production session cookies or mounting old apps.
**What I chose:** Isolated worktree at `archive/pre-cleanup-2026-08-27` (`b14d725`). Write `REPORT-PARITY.md` from code. Do not run `tools/parity` (that tool compares live `/` vs `/test` with cookies). Frozen goldens remain for a later slice. Customer Aging stays BACKLOG.
**Why:** Q6/SQL-only/Q3/Q4 are already decided. Value compare needs fixtures or owner-approved goldens, not production cookies in this leftover.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-04 Phase 9.3 hygiene gate closed
**What I chose:** Close Phase 9.3 on `232866c`. Trust-boundary N/A. Optional Loop C nit (static_dist bundle list vs esbuild) left duplicated.
**Why:** Loops A2+B+C zero blocking. F1 pandas 2.2.3 manylinux_2_17 cp310 closed. Agent Guardrails and GHAS zizmor 4/4 on HEAD. CI and `deploy.ps1` share `tools/build_runtime_artifact.py`. Do not merge.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-04 Stop skipping leftover hygiene
**What I had to decide:** Standing tonight defaults skipped Phase 9–10 and idled after each slice. User asked what is left and why the agent keeps stopping.
**Options I considered:** (1) Stay idle. (2) Invent Q8/Q9 or merge to `main`. (3) Continue remaining non-blocked engineering: Phase 9.3 docs/hygiene, then optional fuller Phase 8 matrix.
**What I chose:** (3). Same draft PR #35. Do not merge. Do not invent Q8 “external” or silent-pick Q9 vs require-edit. Do not unmount `/legacy` `/test` `/test-next`. Do not add a GitHub `production` Environment (still stalls deploys). Phase 7 replica drop still waits on `/test`.
**Why:** “What’s left / why do you keep stopping?” overrides the idle default. 9.3 is specified leftover work with observable gates.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-04 Site responsiveness is overflow, not a redesign
**What I had to decide:** “The responsiveness of the site looks shit” could mean a visual restyle or a layout-overflow fix.
**Options I considered:** (1) Redesign protocol (new look/feel). (2) CSS wrap/`min-width:0` so phone widths do not scroll the document sideways. (3) `overflow-x:hidden` on `html`/`body` only.
**What I chose:** (2). Same leftover PR #35, keep draft. Enable pinch-zoom. Do not restyle colors/type/chrome. Do not hide overflow as the only fix.
**Why:** The broken thing is horizontal overflow and unwrapped toolbars. A redesign was not asked. Hiding overflow would clip controls.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-04 Merge origin/main (0b17176) into PR #35
**What I had to decide:** How to take live save-view modal, custom schedule mail, job-log-for-devs, and Graph 401 refresh without dropping leftover worker/Graph/a11y work.
**What I chose:** Keep both. Delivery-legs stays `0021`. Keep HTTP-only Gunicorn, `enqueue_or_503`, required clock `slot_id`, GraphTokenCache in `graph_auth.py` (not SharePoint `GraphAppToken`), no tenant SharePoint search, dialog helper, live regions including `#reportStatus`, tablist, Tabulator MIT. Take main's product: per-run log page, live saved-view send, save-view modal, custom subject/HTML + sanitizer, admin company-view scheduling, cancel `can_cancel`, `without_delivery_keys`. `pollJobLog` uses `sleepUntilVisible`. Do not restore `beta_sources`.
**Why:** Live `main` is the current site. Leftover 8.15 and Phase 5 Graph cache are this PR's contracts. Duplicate `job_id=` from the merge was dropped.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-04 Saved-view params cannot carry schedule mail HTML
**What I had to decide:** Trust-boundary F1 — salesman plants `email_html` on a saved view, schedule create copies it, admin Edit runs it via `innerHTML`.
**What I chose:** Strip delivery keys when seeding a schedule from a view (`without_delivery_keys`). Same strip on the runner live-view overlay. Sanitize mail fields when copying from an existing row and when rendering `/schedules`.
**Why:** Delivery keys belong on the schedule. Mail send was already sanitized; the hole was the admin editor.
**Status:** DECIDED

## 2026-09-04 SharePoint Test upload 401 while mail still sent
**What you asked for:** Why didn't personal #37 Number 4 land in SharePoint Test?
**What I had to decide:** 401 on `folder D365 F&O` then Graph sendMail ok — permissions vs a dead cached token.
**What I chose:** Dead cached token. SharePoint kept one Graph bearer for the life of the gunicorn worker; Graph mail fetches a new token on every send. Overnight (and any worker older than ~1 hour) the SharePoint bearer is rejected, the 12.9 MB file never uploads, and mail still goes out because recipients were set. Fix: honor `expires_in`, and on Graph 401 drop the cache and retry the folder call once.
**Why:** The log has no site lookup (drive id already cached) and mail succeeded, which is the opposite of a missing SharePoint permission. 403 would be "token works, no access."
**Status:** DECIDED

## 2026-09-03 Schedule emails can have a subject and HTML body
**What you asked for:** Set subject and HTML body for schedule emails, with variables and buttons (SharePoint links). Full featured.
**What I chose:** Per-schedule fields on the personal wizard Where step. Same `{Schedule}` chips as the filename, plus `{SharePointUrl}` and `{DownloadButton}`. Small Bold / SharePoint-link toolbar, no new editor package. Blank = today’s auto mail. Tokens fill in at send time after the file is uploaded.
**Why:** Outlook strips CSS buttons; the app already had a table-cell download button for oversized files. A Word-like editor would be a second stack that mail clients would gut.
**Status:** DECIDED

## 2026-09-03 Company-view schedules keep their source
**What I had to decide:** How to tell a personal schedule of a company view from a personal view of the same name.
**What I chose:** Store `view_source=company` on the schedule params. The runner and the schedules grid resolve company_views first when that flag is set. Personal/default schedules omit it and still prefer the owner's saved view.
**Why:** Name-only lookup sent the personal filters (and could mail the wrong window) when both views were named Collision.
**Status:** DECIDED

## 2026-09-03 Admins can schedule company views
**What you asked for:** Admins and developers should be able to set up schedules using company views.
**What I chose:** Company named views (Daily Ordered, Heshy Open Orders, …) sit in the wizard Company group with Default. `POST /api/schedules` accepts `company:<id>`. The send uses the live company-view filters, same as a personal named view. Salesmen do not see or schedule them. Company (master) add/edit stays hidden.
**Why:** Company views are the shared layouts people actually mail. Default-only in that dropdown left Daily Ordered off the personal wizard.
**Status:** DECIDED

## 2026-09-03 Schedule UI: hide company setup, two-dropdown wizard, dev grid
**What you asked for:** Hide company schedule add/edit (keep the code). Devs see all report runs and schedule history with steps behind a dropdown. Wizard step 1 is salesman/company then views. Home presets collapsed. Devs can edit the schedules grid from a pencil.
**What I chose:** `SHOW_COMPANY_SCHEDULE_SETUP = False` hides Settings button, Add/Edit/Copy/Delete, and the 5-step wizard. Clock jobs and Run now stay. Developers get `?all=1` Recent Reports, all schedule runs on /schedules, and Steps `<details>`. Wizard uses two selects. Home Company views / My presets are `<details>` closed. Pencil toggles recipients/folder inputs.
**Why:** Company setup is moving to personal named-view schedules. Devs still need the old list for Run now and history.
**Status:** DECIDED

## 2026-09-03 Company views can keep a period
**What you asked for:** Saving a company view dropped the period even though you want that option. Save this view used a browser prompt.
**What I had to decide:** Whether the period is always stored, and what lives in the new popup.
**What I chose:** An in-app Save this view modal (name, Save for, “Save the date window”). PUT `/company-views` takes `include_window`. Off or omitted still strips period. Company schedules still send their own period.
**Why:** The old strip was so schedules could pick YTD/MTD/yesterday. That still works. The report-page view should be allowed to remember yesterday when you ask it to. Browser `prompt` is the native alert look.
**Status:** DECIDED

## 2026-09-03 Schedule filename is the email attachment name
**What you asked for:** The filename in schedule setup is not used on the email attachment.
**What I had to decide:** What `{Schedule}` means on a personal schedule, which has no name field.
**What I chose:** Personal named views use the view name for `{Schedule}` (same as the setup preview). Master schedules still use the schedule name. Default view falls back to the report title. The resolved name is the Graph/SMTP attachment filename.
**Why:** The wizard preview used the view name; the runner passed the report title because `Schedule` has no `name`. Default `{Schedule}_{MM}-{DD}-{YYYY}` then mailed `Invoiced_Report_…xlsx` instead of `Yesterday_invoiced_…xlsx`.
**Status:** DECIDED

## 2026-09-03 Job log is developer-only
**What you asked for:** The job log on the report page and everywhere should only be visible to devs.
**What I had to decide:** Whether admin also sees it; whether Cancel and the coarse status line stay; whether the JSON API must hide `log` too.
**What I chose:** Live DB role `developer` only (`authz.is_developer`). Admins, managers, and salesmen do not get the panel, Log button, run-log page, history step log, or `log`/`step` on `GET /api/jobs`. Cancel, recent-run status/rows/summary, and "Building report…" stay. Schedules keep a hidden `#liveJobLog` so poll-until-done still works.
**Why:** The log has API params and first-row samples. That is diagnostic, same as API preview. Hiding only the HTML would still leak it on poll.
**Status:** DECIDED

## 2026-09-03 Personal schedule sends the live view period
**What you asked for:** Avig's yesterday view works on the report page (yesterday + YTD commissions) but the schedule ran all_time. Job log on the report page should collapse.
**What I had to decide:** Whether the schedule row's stored params or the named saved view wins at send time.
**What I chose:** Personal named views send the live saved-view filters (period included). Delivery keys stay on the schedule. Company schedules still use their own period. Report-page job log is a collapsible Job log panel.
**Why:** The GUI always reads the view. The runner used a snapshot copied when the schedule was created, so an edited view (or a leftover all_time snapshot) sent the wrong window.
**Status:** DECIDED

## 2026-09-03 Recent run Log is that job only (hotfix)
**What you asked for:** History under the recent run log was the whole schedule. After reload or opening someone else's job, the log was empty or one mashed line with no fields.
**What I had to decide:** Whether the schedule table History button also becomes per-run.
**What I chose:** Recent run log button is **Log** → `/schedules/runs/<id>` (that run only, Time/Step/Detail). Schedule table **History** stays all-runs. Persist `job_id` on start and `job_log` on success/failure/cancel (`finish` keeps existing `job_id`). Privileged users can open someone else's personal run; a salesman cannot. Reload while running polls the active job into the live log.
**Why:** The recent-run History URL was the schedule history page, live log was session-only, failed finishes wiped the log, and entries were `t — step: detail` on one line.
**Status:** DECIDED — hotfix deviation (self-review + tests; auth on the new route is owner-or-privileged / admin for company).

## 2026-09-04 Phase leftover 8.15 gate closed
**What I chose:** Close leftover 8.15. Trust-boundary N/A. Loop C optional nit left (aria-live ternary also in `admin.ts`/`schedules.ts`; spec forbade a new helper). Representative browser matrix (not 5×4×4 combinatorial) is the Phase 8 leftover evidence; full matrix remains a later Phase 8 gate.
**Why:** Loop A zero. Loop B zero. Loop C zero blocking. `77bdf10` + frontend 33 passed + CDP 6/6 PASS. Did not restyle. Did not split `report.ts`.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent (Loop A Terra; Loops B/C Sonnet)

## 2026-09-04 Finish tonight — defaults (user asked questions then work)
**What I had to decide:** Batch leftover vs blocked product, browser-matrix depth, leftover-vs-merge order, and which chats we can mine.
**What I chose:** Skip Q8/Q9, Phase 7 remainder, Phase 9 archive parity, and Phase 10 merge. Leftover phase is report `#reportStatus` live region plus a representative browser matrix (developer, 320+1280, default+dark). One A/B/C review after that whole leftover, not per todo. Then merge `origin/main` @ `0b17176` keep-both. Follow the user's leftover-first order because `#reportStatus`/`setStatus` match on main. Other-environment chats for PRs #36–#51 are not listed here; git + merged PR titles are canonical. The only other accessible chat with a diff is `bc-9539423f` (sales-rep scope; already on this PR via earlier main merge).
**Why:** User said ask then finish tonight. Those four skips are still BLOCKED or owner/Azure work. Combinatorial matrix is a gate, not a checkbox.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-03 Phase 8.14 gate closed
**What I chose:** Close Phase 8.14. Trust-boundary N/A. Loop C optional nits left (wrap-math vs `moveMenuFocus`; `key`/`event.key` naming matches the caret handler).
**Why:** Loop A F1 (tab id collision) closed `3bcb187`. A re-pass zero. Loop B zero. Loop C zero blocking. Isolated CDP PASS. Did not restyle. Did not split `report.ts`.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-03 Merge origin/main (9a53915) into PR #35
**What I had to decide:** How to combine this PR's leftovers with main's live job log, Cancel for stuck schedule jobs, and `0020_job_log.sql`.
**What I chose:** Keep both. Delivery-legs is `0021_delivery_legs.sql`. Keep HTTP-only Gunicorn, `enqueue_or_503`, Graph token cache, delivery legs, no tenant-wide SharePoint search. Add main's `log_json`, `#jobLiveLog` / `#liveJobLog`, Cancel, and `owner_user_id` on company Run now. Schedule `pollJob` uses `sleepUntilVisible` instead of a bare timeout.
**Why:** Same 0019/0020 collision as last merge. Job-log and Cancel are live product. Do not edit `0019_drop_salesmen.sql`. Incoming tests that assumed `_requests()` tenant search, `announceRun(ok ? …)`, or clock enqueue without `slot_id` were rewritten to this PR's Graph-cache / live-announce / required-slot_id contracts.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-03 Phase 8 leftover: report tablist
**What I had to decide:** How to add WAI-ARIA tablist/tab/tabpanel and arrow keys without breaking Phase 8.5 tab-option menus or restyling the tab bar.
**Options I considered:** (1) `role=tab` on the whole `.report-tab` wrapper (caret would be nested interactive). (2) Label button is `role=tab`; caret stays a sibling `aria-haspopup=menu` button; one shared `role=tabpanel` wrapping pills + table; automatic activation on Arrow/Home/End. (3) Manual activation (arrows move focus only).
**What I chose:** (2). Do not restyle. Do not intercept ArrowDown/Up on the caret. `activateTab` rebuilds the tab strip, so it must restore focus to the selected tab. Unselected tabs `tabindex=-1`; carets stay in tab order.
**Why:** REPOSITORY-REVIEW item 6. Nested interactive inside `role=tab` fails APG. Automatic activation matches in-page sheet switching. 8.5 caret menu stays.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent (spec); implementation spawn Terra

## 2026-09-03 Phase 8.13 gate closed
**What I chose:** Close Phase 8.13. Trust-boundary N/A.
**Why:** Loop A F1 (one unpkg tag could drift) closed `5657caf`. A2 and Loop B zero. Loop C zero. License file GET 200. Did not vendor Tabulator. Ship.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

## 2026-09-03 Phase 8.13: Tabulator MIT text on the report page
**What I had to decide:** Where the leftover “Tabulator MIT license text and third-party attribution” lives.
**Options I considered:** (1) Repo-only NOTICE, no user-visible credit. (2) Vendor Tabulator into static_dist. (3) Serve the 6.3.1 MIT text at `/static/licenses/tabulator-MIT.txt` and credit it on `report_view.html` (the only page that loads Tabulator). (4) A Settings “open source” page for every CDN dep.
**What I chose:** (3). Do not vendor. Do not add Feather in this leftover. Do not add a Settings licenses page.
**Why:** MIT requires the copyright and permission notice with the software. Attribution belongs where the library is used. Settings would be a second product surface the leftover does not ask for.
**Status:** DECIDED
**Model:** cursor-grok-4.6
**Runner:** parent

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
## 2026-09-03 Cancel stuck schedule jobs
**What you asked for:** A cancel for scheduled reports too, so a stuck job can be cleared for other jobs and tests.
**What I had to decide:** Who may cancel a clock job with no owner; whether cancel kills an HTTP call already in flight.
**What I chose:** Reuse `POST /api/jobs/<id>/cancel`. The schedule owner can cancel their jobs. Admins/developers can cancel any `schedule.run`, including company clock jobs with no owner. Report runs stay owner-only. Cancel next to Run now, plus an in-progress list on the run log. Cancel marks the job cancelled immediately (frees the clock dedup so a new run can enqueue). An API call already in flight still finishes; the worker stops before the next call and does not mark success/failure over the cancel.
**Why:** Run now had no Cancel, and clock jobs with `owner_user_id` NULL were invisible to the user APIs, so a stuck send sat in the queue and blocked the next tick.
**Status:** DECIDED

## 2026-09-03 Granular live job log
**What you asked for:** The live log only showed three steps. Need to see exactly what the job is doing: building this tab, that tab, and what the API response was.
**What I had to decide:** Whether to dump full Reporting API rows into sqlite; how the screen shows the log.
**What I chose:** A scrolling list of every log entry, not just the latest status line. Each API call logs the params sent, then HTTP status, timing, row_count vs len(rows), columns, byte size, date span, and a truncated first-row sample. Month chunks, invoiced YTD-vs-period, each tab name + row count, each Excel sheet, each SharePoint folder create (201 vs 409), and sendMail ok/error all get their own lines. Cap is 250 entries / 2000 chars. Full raw rows stay out of the job log (`RAW_CAPTURE_*` still exists for that).
**Why:** The status line was the last coarse step (`job` / `report` / `workbook`). Fake test clients also skip HTTP, so even the API line often never appeared in tests. The UI hid everything except that last string.
**Status:** DECIDED

## 2026-09-03 Live job steps; stop searching every SharePoint site on first save
**What you asked for:** Invoiced-yesterday does not take this long. Figure out why the job stayed running after SQL finished. Maybe a new schedule's first SharePoint save.
**What I had to decide:** Whether I can see this live job from the agent VM; what to store in the live log; what to do when SP_SITE_URL is wrong.
**What I chose:** This VM still cannot read Azure logs or precious.db, so this exact run is gone. After SQL returns, `schedule.run` still does workbook + Graph. v3 SharePoint, on the first Graph use of a worker (deploy recycle, or a new folder save that is the first upload), resolved the drive by searching every tenant site named "achim" whenever SP_SITE_URL was not HTTP 200 — 30s per site, no cap. Legacy already failed loud on 404; v3 did not. A new schedule's `_ensure_folder` is extra Graph POSTs on top of that. I stop the search when SP_SITE_URL is set (raise with the HTTP status). Empty URL (local) may search at most 5 sites / 45s. Jobs get a live `log_json` the UI polls (report status line, Run now button, history). Graph mail token uses the same 30s HTTP POST as SharePoint so msal cannot hang with no timeout. The log stores timings and counts, not the raw API row payload.
**Why:** Your first-SharePoint guess is the only path in this app that runs after the DBA's query returns and can sit in `running` for many minutes without a SQL excuse. Without a live step log we would keep guessing.
**Status:** DECIDED
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

Older entries: DECISION-LOG-ARCHIVE.md
