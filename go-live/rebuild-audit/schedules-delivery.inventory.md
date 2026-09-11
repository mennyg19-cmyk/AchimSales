Model: gpt-5.6-sol-medium
Runner: spawn
Area: schedules-delivery
Role: inventory
Graph: graph via parent digest

## Proof of read

- `AUDITOR-INSTRUCTIONS.md`: production scope is `/workspace/v3`, application code is read-only, and this inventory must be opened by proof rather than recommendations.
- `graph-backbone/INDEX.md`: the live Flask app has four audit areas, four named worker job types, and four roles; Beta shares the Live cookie but omits the dashboard blueprint.
- `graph-backbone/schedules-delivery.md`: I found 23 schedule routes, three precious tables, four scheduling helpers, and three delivery channels (email, SharePoint, OneDrive).
- Named-file drill-down covered both schedule row types, the run ledger, 3 cadence frequencies, 15 filename tokens, 5 schedule templates, and 3 TypeScript entry/modules.

## Product surfaces and permissions

### Personal schedules

- `GET /schedules`: one grouped table. Non-privileged users see only their own rows; admins/developers see all personal rows grouped by owner.
- The table preserves report, saved view, cadence, recipients, folder, last run, active state, and actions: Edit, Run now, Copy, History, Delete.
- The 3-step wizard is View → When → Where. A new schedule is active by database default. A copy preserves all stored settings, gets a new row, and is forced inactive.
- Create/update/toggle/delete/run/copy endpoints are owner-scoped, except privileged users may operate on another owner's personal row. Personal report runs are re-authorized against the owner's current account and report access.
- A personal schedule is tied to the saved view owner's user id and runs with that person's row visibility. Non-privileged users can only schedule their own eligible named views.
- Privileged users can select eligible views belonging to active users and can also schedule the `Default` view of any visible built, non-in-app report.

### Company schedules

- `GET /settings/company-schedules`: admin/developer-only list and 5-step wizard: Report → When → Options → Where → Review.
- `GET /master-schedules` is a redirect alias to the Settings page.
- The table preserves name, report, view, cadence, option summary, recipients, folder, last run, active state, and actions: Edit, Copy, Run now, History, Delete. It is client-sortable by every non-action column.
- Master rows require admin/developer access. Edit/toggle/delete/copy/run additionally use `can_edit_master`, based on owner and optional run-as user.
- A company schedule can be private or shared with admins/managers. Sharing controls visibility, not report scope.
- `run_as_user_id` may point to an active manager. That schedule uses the manager's book. With no run-as manager, a privileged-owned master schedule is company-wide/unscoped.
- Copy preserves report, params, layout, cadence, recipients, folder, filename, sharing, run-as, and view; assigns the copier as owner; generates `Name (copy)`, then `(copy 2)` etc.; and starts inactive.
- Deleting or renaming a seeded company schedule updates the seed skip/unskip setting so boot seeding does not silently restore an intentionally removed old name.

### Route inventory (23)

1. `GET /schedules`
2. `GET /api/schedules/recent-runs`
3. `POST /api/schedules`
4. `PUT /api/schedules/<id>`
5. `POST /api/schedules/<id>/toggle`
6. `DELETE /api/schedules/<id>`
7. `POST /api/schedules/<id>/run`
8. `POST /api/schedules/<id>/copy`
9. `GET /api/schedules/views`
10. `GET /schedules/<id>/history`
11. `GET /master-schedules/<id>/history`
12. `GET /settings/company-schedules`
13. `GET /master-schedules`
14. `GET /api/master-schedules/lookups/status`
15. `GET /api/master-schedules/lookups/salesmen`
16. `GET /api/master-schedules/lookups/salesmen-emails`
17. `GET /api/master-schedules/lookups/customers`
18. `POST /api/master-schedules`
19. `POST /api/master-schedules/<id>/copy`
20. `PUT /api/master-schedules/<id>`
21. `POST /api/master-schedules/<id>/toggle`
22. `DELETE /api/master-schedules/<id>`
23. `POST /api/master-schedules/<id>/run`

## Stored fields that must survive

### `schedules` / personal row (18 logical fields)

| Field | Meaning |
|---|---|
| `id` | Schedule identity |
| `owner_user_id` | Saved-view owner and runtime authorization identity |
| `report_key` | Report registry key |
| `params_json` / `params` | Report filters plus delivery flags |
| `layout_json` / `layout` | Saved grid/export layout snapshot |
| `cadence` | JSON cadence object |
| `recipients` | Validated comma-normalized To addresses |
| `sharepoint_path` | Shared storage column: personal OneDrive path by default, or SharePoint path when `folder_kind=sharepoint` |
| `is_active` | Cron eligibility / On-Off state |
| `start_date` | Optional schedule validity start, accepted by the API even though the current wizard does not expose it |
| `end_date` | Optional schedule validity end, accepted by the API even though the current wizard does not expose it |
| `created_at` | Creation timestamp and list ordering input |
| `filename_template` | Workbook filename template |
| `catch_up_pending` | A Sabbath/Yom Tov makeup is owed |
| `catch_up_for_date` | Earliest skipped Eastern date still owed |
| `last_claimed_at` | Claimed cadence slot, preventing save/toggle-on from backfilling the current slot |
| `view_name` | `Default` or the backing named personal view |
| derived `folder_kind` in params | `onedrive` or `sharepoint`; defaults to OneDrive for old personal rows |

### `master_schedules` / company row (18 logical fields)

| Field | Meaning |
|---|---|
| `id` | Schedule identity |
| `report_key` | Report registry key |
| `name` | Required schedule name, maximum 120 in the UI/copy naming logic |
| `params_json` / `params` | Whitelisted report filters and delivery controls |
| `layout_json` / `layout` | Default/custom/named-view layout snapshot/fallback |
| `cadence` | JSON cadence object |
| `recipients` | Validated comma-normalized To addresses |
| `sharepoint_path` | Shared storage column: SharePoint or private OneDrive path, disambiguated by `folder_kind`/sharing |
| `is_active` | Cron eligibility / On-Off state |
| `created_at` | Creation timestamp |
| `filename_template` | Workbook filename template |
| `owner_user_id` | Creator/owner used by edit rights and as a possible runtime scope |
| `is_shared` | Private versus visible to admins/managers |
| `run_as_user_id` | Optional manager whose book scopes the run |
| `catch_up_pending` | A Sabbath/Yom Tov makeup is owed |
| `catch_up_for_date` | Earliest skipped Eastern date still owed |
| `last_claimed_at` | Claimed cadence slot |
| `view_name` | `Default`, `Custom`, personal preset name, or company-view name |

### `schedule_runs` ledger (9 fields)

`id`, nullable `schedule_id`, polymorphic `schedule_type` (`personal`/`master`), `status`, `started_at`, `finished_at`, nullable `rows`, JSON `output_meta`, and `debug_log`.

Run metadata preserves summary, outbox id, `.eml` artifact, actual-mail flag (`sent_smtp`, legacy name), channel, SharePoint saved/url/error, recipients, error, and optional per-delivery fan-out legs.

## Report and delivery parameters

The schedule payload/storage must retain these parameter families:

- Report windows: `period`, `year`, `start_date`, `end_date`; old custom personal views may also contain `from`/`to`.
- Multi-select report filters: `status`, `salesman`, `customers`.
- Salesman fan-out: `email_to_salesmen`, `split_by_salesman`, `email_salesman_keys`.
- Mail: `email_cc`, `email_bcc`, `email_on_no_data`, `email_on_no_data_me_only`.
- Storage/Sabbath: `folder_kind`, `skip_sabbath`.
- Runtime-only report restriction: `_skip_commissions` for an invoiced report whose effective viewer may not see commissions.

Master APIs intentionally whitelist these keys. Unknown master params are discarded on save. Delivery-only keys are stripped before report generation.

### Report-specific master options

| Report | Options exposed |
|---|---|
| `ordered` | period, status, customers, salesman |
| `invoiced` | period, customers, salesman |
| `salesman` | year, salesman |
| `number_4` | none |
| `customer_activity` | salesman |
| `sales_by_state` | year |

Period choices are Yesterday, Month to Date, Last Month, Year to Date, This Week, Last 7 Days, and All Time. Status choices are Open order, Delivered, Invoiced, and Cancelled; an empty selection means all statuses. Year offers current year through four prior years.

Salesmen and customers come from customer-master lookups and are restricted to salesmen visible to the acting principal. The email-salesman picker only includes salesmen with a stored email.

## Cadence

- Frequencies: `daily`, `weekly`, `monthly`.
- Every cadence stores Eastern `time` as `HH:MM`, defaulting to `08:00`.
- Weekly stores sorted/deduplicated `weekdays`, Monday `0` through Sunday `6`, and requires at least one.
- Monthly stores sorted/deduplicated `monthdays`: days `1..28` and `-1` for the calendar month's last day. Legacy `monthday` remains accepted and is written as the first selected day for old readers.
- Due checks use `America/New_York`, wait until the scheduled clock time, require the matching weekday/monthday, and allow at most one run per Eastern calendar day.
- A save or toggle-on claims a currently due slot through `last_claimed_at`, preventing an immediate accidental catch-up send.
- Start/end dates are stored for personal schedules and must continue to constrain tick eligibility even though they are not visible in the current wizard.

## Sabbath, Yom Tov, and catch-up

- Automatic runs skip by default. `params.skip_sabbath=false` opts out. `Run now` explicitly sets `ignore_sabbath=true`.
- Restriction is determined from Hebcal for Brooklyn (`geonameid=5110302`), using candle/havdalah windows and Yom Tov markers. The lookup spans four days back to three days forward, caches by window, has a 10-second timeout, and fails open.
- A restricted automatic run is ledgered as `skipped`, marks catch-up pending with the earliest owed Eastern date, and does not send at havdalah.
- `skip` class waits for the next regular cadence slot. `reschedule` class waits for the next unrestricted Monday-Friday occurrence of the same clock time.
- Always reschedule: all-time reports `customer_activity` and `salesman`; periods `last_7_days`, `this_week`/`week`, `last_month`/`month`.
- MTD/YTD reschedule only when the cadence cannot self-heal on a later Sunday-Thursday slot before month/year end. Other periods skip to the next regular slot.
- Yesterday/daily catch-up spans from last success (or skipped day) through yesterday. MTD can emit two windows across month-end: skipped partial month and complete month. YTD closes the prior year when crossing year-end. Week and last-month classes create custom windows that retain missed data.
- Catch-up and regular windows may both run; duplicate `(period,start_date,end_date)` windows are removed. Custom windows append their end date to subject and schedule name so files cannot collide.
- A successful catch-up clears the pending flag. A recovered job skips if that schedule already succeeded today.

## Saved views and workbook layout

### Personal Default versus named

- Normal users can schedule named personal saved views only. Empty names, `Default`, company views, and custom date ranges are absent from Add.
- Admins/developers additionally get synthetic `default:<report_key>` choices for visible built reports that are not in-app reports.
- Default creation uses incoming `params` when supplied, otherwise the current report-default params; it rejects custom dates and stores `view_name=Default`, `layout={}`.
- A named personal schedule snapshots the preset's params and layout at creation. On edit, it refreshes params/layout from the currently backing saved view when that view still exists.
- Converted legacy custom-date views remain runnable and editable on their existing schedule through a locked picker card, but stay unavailable for new schedules.
- If a personal schedule's backing view is missing, the row retains its stored `view_name`, params, and layout; the edit UI keeps it represented as a locked/imported choice.

### Company Default versus named

- The View picker starts with `Default`, then company views, then report presets. An existing unknown view is restored as a `Custom`/named option instead of being silently reset.
- A selected preset copies its period/year/status/salesman/customers and layout into the wizard. The selected name is stored in `view_name`.
- At send time, `ScheduleRunner._layout_for` calls `resolve_send_layout` with the stored view name, stored schedule layout, current report-default layout, and the current company-view layout when the name is non-Default.
- Named company layouts are therefore live lookup inputs at send time; stored layout remains a fallback. Default continues to resolve against the current report default. Preserve this distinction.
- Canonical company views are `Daily Ordered` and `Heshy Open Orders`. Boot upserts both and stamps matching schedules unless they already point at a different explicit named view.
- `Daily Ordered`: active `by_customer`; tab order `summary`, `by_customer`, `by_item`, `by_order`, `by_salesman`, `full_data`; defined salesman/customer/item sorts and groups.
- `Heshy Open Orders`: Ordered, yesterday, Hkaufman, Open order; active/full-data-only layout grouped by sales order with an explicit column list, `LineNumber` hidden, customer/order sorting.
- Company-view date keys (`period`, `start_date`, `end_date`, `from`, `to`) can be removed so the schedule's own Yesterday/MTD/YTD window remains authoritative.

### Layout semantics delivered to Excel

- Layout includes active tab, tab `order`, `views`, and optional `clones` (`key`, `baseKey`, `name`).
- A non-empty tab order is an include-list: omitted tabs do not appear in the workbook. Clone tabs are deep copies of their base tabs and receive their own layout.
- Per-tab delivery applies hidden columns, explicit column order, `columnFilters`, legacy `headerFilters`, and stable multi-sort.
- String filter operators: contains/default, equals, starts, ends, in, empty, notEmpty. Numeric: eq, ne, gt, ge, lt, le, between. Date: on, before, after, between.
- Viewer-only grouping and freeze settings do not flatten into the workbook, though group data remains part of named layouts. Number 4 month columns receive special ordering before totals/prices/salesman.

## Recipient, CC/BCC, and no-data behavior

- To/CC/BCC parse comma or semicolon lists and accept only strings matching a basic `name@domain.tld` shape.
- Personal To defaults to the saved-view owner's email. Non-privileged users cannot add extra To, CC, or BCC. Privileged users can disable owner mail, add extra To, and set CC/BCC.
- The owner is de-duplicated from privileged extra To addresses. A personal schedule needs owner email or a folder.
- Company schedules allow arbitrary validated To, CC, and BCC. A schedule needs To, a folder, or a salesman fan-out target.
- `email_on_no_data=false` skips workbook email/folder delivery when total rows are zero and records a successful skip.
- `email_on_no_data=true` sends normal recipients on zero rows.
- `email_on_no_data_me_only=true` sends zero-row mail to configured test addresses, suppressing CC/BCC for that empty send, unless normal no-data mail is also enabled.
- Master salesman fan-out has two modes: selected report salesmen + `email_to_salesmen`, or unfiltered `split_by_salesman`/explicit `email_salesman_keys`. Each gets a workbook filtered to that salesman.
- The management To/folder leg still receives the full workbook. Missing salesman email skips that split without failing a management send. A zero-row salesman split becomes a text-only “No Data Found” notice.
- Preserve a current edge: the ordinary non-fan-out path passes stored CC/BCC into delivery, but `_run_master_fanout` does not pass CC/BCC on its full management leg. Rebuilding should not accidentally claim fan-out CC/BCC works without deciding whether to fix this behavior.

## Run now, retries, failures, and history

- Run now exists for both personal and company rows, works regardless of active state, queues `schedule.run`, and bypasses Sabbath/Yom Tov. Company Run now still requires edit authorization.
- In non-production with no running worker, the request drains the worker synchronously. The UI opens Recent run log, queues the run, refreshes every 1.5 seconds for up to 90 seconds, and restores the button after completion/poll timeout.
- Each execution starts a `running` ledger row, then finishes `success`, `failure`, or `skipped`, preserving row count and details.
- Each delivery window gets up to 2 attempts with a 30-second wait. A retry success changes the subject with “retried after a failure” and adds the first error to the body.
- A failure notice is held for 15 minutes. A later success supersedes it; otherwise `[FAIL]` mail goes to configured test addresses, even when company test mode is off.
- Multiple catch-up windows continue after an individual window failure. The run only fails if none succeed; mixed window success is recorded in the summary.
- Personal Recent run log contains only allowed personal rows. Company log is admin-only. Both show time, schedule kind/title, status, rows, message, and History link.
- History shows status, start/finish, rows, summary/debug log, recipients, channel, `.eml`, outbox id, SharePoint result/error, failure error, and every full/split delivery leg.
- The history back-link currently always targets `/schedules` (master adds `#company`) even though the company UI lives at `/settings/company-schedules`; preserve intentionally or correct during rebuild, but do not lose history access.

## Email delivery

- Every attempted email composes RFC-822 and writes a uniquely suffixed `.eml` artifact before transport, then records an outbox row.
- Microsoft Graph is preferred when tenant/client secret/from-address exist. SMTP is fallback only when Graph is not configured, not when Graph returns an error. With neither, the channel is `outbox`: the artifact is retained but no inbox receives it.
- Graph attachment threshold is raw workbook `< 2,500,000` bytes. Larger workbooks upload first and send link-only plain/HTML mail with an Outlook-safe Download workbook button.
- A Graph size rejection (413 or known size text) retries once without attachment, uploading to the Test folder if no usable URL exists.
- If mail reached an inbox but optional folder upload failed, delivery remains successful and records the folder error to avoid duplicate retry mail. A folder-only upload failure is fatal.
- Delivery subjects are `Scheduled: <name> (<UTC YYYY-MM-DD>)` for personal and `Master: <name> (<UTC YYYY-MM-DD>)` for company. Test mode prefixes `[TEST]`.
- Company test mode replaces stored recipients with configured test addresses, suppresses CC/BCC, disables OneDrive identity, and redirects a configured SharePoint path to `Direct Reports/Test`. Salesman splits still run but go to the test list.

## Filename and folder templates

- New/blank default: `{Schedule}_{MM}-{DD}-{YYYY}`; output is always `.xlsx`, filesystem-safe, and capped at 180 characters.
- All 15 tokens: `{YYYY}`, `{YY}`, `{MM}`, `{M}`, `{Month}`, `{Mon}`, `{DD}`, `{D}`, `{HH}`, `{mm}`, `{ss}`, `{Report}`, `{Schedule}`, `{Period}`, `{Weekday}`.
- Date/time tokens use Eastern time. Report and schedule values are filename-safe slugs. `{Period}` uses `params.period`, then `params.year`, then `YYYYMMDD`.
- Unknown tokens remain visible instead of disappearing. Illegal filename characters collapse to `_`.
- Folder templates use the same tokens, retain spaces and `/` hierarchy, remove Graph-illegal characters, and discard empty/dot segments.
- Both personal and company wizards show live filename previews and token insertion chips. Company SharePoint also previews folder templates and offers month/year chips.

## SharePoint

- Company shared storage is SharePoint; personal SharePoint is privileged-only. A private company row may choose SharePoint or OneDrive.
- Paths are relative to configured drive root plus `Direct Reports`. Repeated user-entered `Direct Reports` prefixes are stripped.
- Folder picker/listing and uploads use Microsoft Graph app credentials. Production fails loudly if unconfigured; non-production uses mock trees/uploads.
- Upload validates every path/file segment against traversal (`.`/`..`), separators, and Graph/OneDrive reserved characters.
- Missing folder segments are created one by one; existing-folder conflict 409 is accepted.
- Small files use direct content upload and large-file handling is delegated to the shared Graph upload helper. Returned `webUrl` feeds download-link email.
- Test-mode company writes target the `Test` subfolder when the stored schedule has a cloud path.

## OneDrive

- Personal OneDrive is the default folder type. Upload runs app-only under `/users/{owner-email}/drive`, allowing overnight writes without an interactive login.
- Private company OneDrive uses the effective identity (run-as manager or owner). Shared company schedules default to SharePoint unless `folder_kind` explicitly says OneDrive.
- OneDrive and SharePoint are mutually exclusive in each wizard. The UI supports breadcrumb browsing and explicit “Use this folder,” including OneDrive root.
- OneDrive validates the user email and reuses SharePoint's path-segment safety checks. Production fails if unconfigured; non-production uses mock folders/uploads.
- Required Graph permission called out in code: `Files.ReadWrite.All` with admin consent.

## Preserve checklist

- [ ] All personal/master/run fields above migrate without collapsing the shared path column or losing `folder_kind`.
- [ ] Personal owner scoping and runtime re-authorization remain fail-closed.
- [ ] Company private/shared visibility remains separate from run-as/report scope.
- [ ] Daily/weekly/multi-day monthly cadence stays Eastern and preserves legacy `monthday`.
- [ ] Sabbath default-on, Run now bypass, earliest owed date, period classification, custom catch-up windows, and slot claims survive.
- [ ] Named personal eligibility, privileged Default choices, locked legacy custom views, and owner grouping survive.
- [ ] Default layouts remain live report defaults; named company layouts remain live company-view lookups with stored fallback.
- [ ] Clone tabs, include-list tab order, hidden/order/filter/sort export behavior survive.
- [ ] To, privileged personal extras, CC/BCC, both no-data modes, salesman fan-out, and test recipients survive.
- [ ] Filename/folder templates retain every token, Eastern expansion, previews, sanitization, and default.
- [ ] Run now, active toggle, copy-inactive, delete confirmation, recent polling, and full history metadata survive.
- [ ] Graph/SMTP/outbox behavior, 2.5 MB link fallback, delayed failure notice, retries, and no-duplicate semantics survive.
- [ ] SharePoint `Direct Reports` rooting/Test redirect and personal/private OneDrive identity survive.

## Extra CodeGraph queries I would have run

CodeGraph CLI was unavailable. With an index, I would have queried callers/impact for `ScheduleRunner.run`, `ScheduleRepository`, `MasterScheduleRepository`, `resolve_send_layout`, `run_param_windows`, `DeliveryService.run_and_deliver`, `EmailService.deliver`, and both Run now route handlers; and explored the cron/tick path that consumes `start_date`, `end_date`, `last_claimed_at`, and catch-up fields.
