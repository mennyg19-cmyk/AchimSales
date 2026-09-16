# Normalized views, layouts, and schedules

Status: **locked 2026-09-15** (Gate A + dual-write + Gate B fixture workbooks green; live reads use assembled tables; scheduled/emailed deliveries use the new layout and silently dual-build the old JSON workbook for parity).

## Silent dual-build + daily digest (live)

Every scheduled/emailed report delivery:

1. Builds and sends the workbook from the **new** (assembled) layout.
2. Also builds the **old** `layout_json` workbook under `{precious parent}/view-parity/YYYY-MM-DD/` (or `VIEW_PARITY_DIR`), as `__new.xlsx` / `__old.xlsx`.
3. Compares sheet cell grids and writes a row to `view_workbook_parity`.

Parity never fails the real send. Toggle off with app_settings `view_workbook_parity=0`.

Once a day (Eastern **7:05**), the scheduler emails yesterday’s match/diff scores to `view_parity_digest_emails` (fallback: schedule test emails, then `V3_ADMIN_EMAILS`). Idempotent per Eastern day (`view_parity_digest_sent_day`).

Manual one-shot still available:

```bash
cd v3
PRECIOUS_DB_PATH=/path/to/precious.db \
REPORTING_API_BASE_URL=… REPORTING_API_KEY=… \
python -m tools.compare_view_workbooks
```

Writes `.scratch/view-workbook-compare/<stamp>/` with both xlsx files + INDEX.md.

This replaces three view tables and the layout/params copies on schedules with one `views` tree. The report page and the clock job both read that tree. JSON blobs stay on jobs, notifications, and job logs.

Old tables stay until cutover: `saved_reports`, `company_views`, `report_defaults`, `schedules`, `master_schedules`.

## Product rules (locked)

- A **view** is filters + grid layout for one report. Personal, company named, and company Default are the same table (`kind`).
- A **schedule** is when/where/who. It points at one `view_id`. It does not copy layout or filters.
- Company/master **period** (YTD / MTD / yesterday) lives on the schedule. The view may also store a window for the GUI and for personal named-view sends. Same rule as today, without copying the rest of the filters.
- Delivery fields never live on a view: recipients, cc/bcc, folder kind, email subject/html, filename, SharePoint path, split-by-salesman, skip Shabbos.
- Empty grouping is zero rows in `layout_tab_groups` on a tab that **exists** with `groups_explicit=1`. That is `group: []`. A tab with `groups_explicit=0` omits the `group` key (builder default). A missing tab row also means “builder default,” not ungroup.
- Delete a view that a schedule still points at → SQLite error (RESTRICT). Delete an unused view → tabs/columns go with it (CASCADE).

## Readable ids

TEXT primary keys. Unique. Human.

| Row | Pattern | Example |
|---|---|---|
| User handle | first initial + last name, lowercase alnum. Collision → `mgrego2` | `mgrego` |
| Default view | `df-{report}` | `df-ordered` |
| Company view | `co-{report}-{slug}` | `co-ordered-daily-ordered` |
| Personal view | `pe-{handle}-{report}-{slug}` | `pe-mgrego-ordered-open-orders` |
| Tab | `{view_id}__{tab_key}` | `co-ordered-daily-ordered__summary` |
| Column | `{tab_id}__{slug(field)}` | `…__summary__customer-name` |
| Group / sorter / filter | `{tab_id}__g{n}` / `__s{n}` / `__f-{slug(field)}` | `…__g2` |
| Schedule | `{handle-or-co}-{report}-{freq}-{time}` | `mgrego-ordered-daily-0800` |

`users.handle` is added on the existing users table (unique). Old tables keep integer `users.id`. New tables FK to `users.handle`. Integer ids go away when the old tables drop.

Handle algorithm: take `display_name` (“Meir Grego” → `mgrego`); if blank, email local-part stripped to alnum; if collision, append `2`, `3`, … Email stays unique for login.

Slug: lowercase, non-alnum → `-`, collapse dashes, trim, cap length so the full id stays readable in the explorer.

## New tables

Foreign keys are ON (already). Every child holds the parent id. Do not store both `view_id` and `tab_id` on columns.

### `views`

| Column | Notes |
|---|---|
| `id` | TEXT PK |
| `kind` | `personal` \| `company` \| `default` |
| `report_key` | TEXT NOT NULL |
| `name` | TEXT NOT NULL |
| `owner_handle` | TEXT NULL FK `users(handle)` ON DELETE CASCADE. Null for company/default |
| `period`, `start_date`, `end_date`, `year`, `mode` | scalar filters, nullable |
| `active_tab_key` | TEXT NULL. Matches `layout_tabs.tab_key` (no circular FK to tab id) |
| `updated_at`, `updated_by_handle` | SET NULL on user delete for company rows |

Unique: `(kind, owner_handle, report_key, name)` with `owner_handle` null for company/default (SQLite unique + nulls: use a unique index on `report_key` WHERE `kind='default'`, and `UNIQUE(report_key, name)` WHERE `kind='company'`).

### List filters (no JSON arrays)

- `view_salesmen (id, view_id, salesman)` unique `(view_id, salesman)`
- `view_statuses (id, view_id, status)` unique `(view_id, status)`
- `view_customers (id, view_id, customer_account)` unique `(view_id, customer_account)`

FK `view_id` → `views(id)` ON DELETE CASCADE.

### `layout_tabs`

| Column | Notes |
|---|---|
| `id` | TEXT PK |
| `view_id` | FK CASCADE |
| `tab_key` | `by_customer`, `summary`, clone keys, … |
| `position` | 1-based on-screen / Excel sheet order (`layout.order`); NULL if the tab is not in `order` |
| `clone_of_tab_key` | NULL unless this is a duplicated tab (`clones[].baseKey`) |
| `tab_name` | clone display name; NULL = report default name |
| `has_view` | 1 if the tab was in `layout.views` (so zero group rows means `group: []`) |

Unique `(view_id, tab_key)`.

A tab row exists when the old JSON listed it in `views`, `order`, `active`, or `clones`. That is how we tell **explicit ungroup** (tab row, zero group rows) from **omitted tab** (no row, builder default).

### Ordered lists on a tab

`layout_tab_groups (id, tab_id, position, column_name)` — nest order. Zero rows = `group: []`.

`layout_tab_sorters (id, tab_id, position, column_name, dir)` — `dir` CHECK `asc`\|`desc`.

FK `tab_id` → `layout_tabs(id)` ON DELETE CASCADE. Unique `(tab_id, position)` on each.

### `layout_columns`

| Column | Notes |
|---|---|
| `id` | TEXT PK |
| `tab_id` | FK CASCADE |
| `field` | column field name as the payload uses it |
| `position` | order in the tab; NULL if hidden and not in `order` |
| `hidden` | 0/1 |
| `frozen` | 0/1 |
| `width` | REAL NULL |

Unique `(tab_id, field)`. Store a row only when the saved layout mentions that field (in `order`, `hidden`, `frozen`, or `widths`). Other columns come from the report payload at run time.

### `layout_column_filters`

`id`, `tab_id`, `field`, `op`, `v`, `v2`. Unique `(tab_id, field)`. FK CASCADE.

### `report_schedules` (new; old `schedules` / `master_schedules` stay)

| Column | Notes |
|---|---|
| `id` | TEXT PK |
| `kind` | `personal` \| `company` |
| `view_id` | FK `views(id)` **ON DELETE RESTRICT** |
| `owner_handle` | FK users. Company rows may be null |
| `name` | company display name; personal can equal the view name |
| `freq` | `daily` \| `weekly` \| `monthly` |
| `time` | `HH:MM` Eastern |
| `window_period`, `window_start`, `window_end` | company send window (YTD / MTD / yesterday). Fallback when the view has no window |
| `sharepoint_path`, `filename_template` | |
| `folder_kind` | `onedrive` \| `sharepoint` |
| `email_subject`, `email_html` | blank = auto mail |
| `email_on_no_data`, `email_on_no_data_me_only` | 0/1 |
| `split_by_salesman`, `email_to_salesmen`, `skip_sabbath` | 0/1 |
| `run_as_handle` | company run-as |
| `is_shared`, `is_active` | |
| `active_from`, `active_until` | schedule lifetime (today’s start_date / end_date on the row) |
| `catch_up_pending`, `catch_up_for_date`, `last_claimed_at`, `created_at` | |

No `report_key` on this table — join `views`. No `layout_json` / `params_json` / `cadence` JSON.

Children:

- `schedule_weekdays (schedule_id, weekday)` 0=Mon … 6=Sun
- `schedule_monthdays (schedule_id, monthday)` 1–28 or -1 = last day
- `schedule_recipients (id, schedule_id, email, role)` role = `to`\|`cc`\|`bcc`
- `schedule_email_salesmen (schedule_id, salesman)` today’s `email_salesman_keys`

## What stays JSON (out of scope)

`jobs.params_json`, `jobs.log_json`, `notifications.payload_json`, `schedule_runs.output_meta`, `outbox` meta.

## Coexistence and cutover (locked)

1. **Add tables + backfill.** Old JSON remains the live path. One-way projector: old row → new rows. Round-trip test: new rows → assemble the old layout/params dict → canonical JSON equals the source (same keys the exporter already understands).
2. **Report builder on the new tables.** Save this view / explorer edits write the new tables. Keep dual-writing the old JSON so today’s GUI and clock still run. For every saved view, run **both** builders (new assemble vs old JSON) and require a match.
3. **Live read + silent dual delivery.** Deliveries use assembled layout. Old JSON workbook is still built to disk and scored (`view_workbook_parity` + daily digest email). Watch scores for about a week of green digests.
4. **Cut over.** Stop writing old JSON. Then drop `params_json` / `layout_json` / `cadence` JSON and the three old view tables / two old schedule tables.

Do not drop old tables in step 1–3.

## Snapshot schedules (locked)

Today a Default (or `Custom`) schedule can freeze a layout copy so a later Default edit does not change that file.

There are no copies on the new schedule row. On backfill, if a schedule’s stored layout/params differ from the view it names, create a **personal view** for that owner (`pe-…`) with that snapshot and point the schedule at it. If they match, just store `view_id`.

## Parity (what “matches” means)

**Gate A (required before the builder writes new):** for every `saved_reports` / `company_views` / `report_defaults` row, `assemble(new_rows) == canonicalize(old_json)` for both `params` and `layout`.

**Gate B (required before cutover):** for a fixture set of views (Daily Ordered, Heshy Open Orders, one personal Ordered, one Number 4, one ungrouped By Order), build the workbook from the new assemble and from the old JSON; workbooks match on sheet names, column order, grouping, hidden columns, sort, and filters. Not pixel-identical Excel XML.

Canonical JSON: stable key order, `group: []` present on stored tabs, no delivery keys on views.

## Out of this spec

Live `/legacy` (`webapp/`) schema. Rebuild `/test-next`. `schedule_runs` history mapping (integer polymorphic ids → new TEXT ids) is a cutover follow-up: add nullable `report_schedule_id` when the new clock writes runs; backfill at drop time.

## Locked answers (2026-09-15 “yes to all”)

1. During step 2, old JSON stays live until Gate A is green. The new builder dual-writes.
2. Report builder = Save this view + explorer on the new tables, not a second app.
3. Cadence and recipients are tables in step 1.
4. Gate B fixtures: Daily Ordered, Heshy Open Orders, one personal Ordered, one Number 4, one By Order with `group: []`.
5. User handle may match a salesman key. Do not suffix just because a salesman exists.
