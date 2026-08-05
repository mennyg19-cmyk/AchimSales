# Decision Log

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
