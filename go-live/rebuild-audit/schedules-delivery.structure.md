# Structure audit: schedules-delivery

Model: claude-fable-5-1-thinking-medium
Runner: spawn
Area: schedules-delivery
Role: structure
CodeGraph: `codegraph status` → command not found; **graph via parent digest**.

## Proof-of-read

- AUDITOR-INSTRUCTIONS.md: 37 lines; scope = live `v3/` only, Phase 0 Step 2, no rewrite, no app-code edits, deliverable header + ≤10-line reply.
- graph-backbone/INDEX.md: 4 area digests, 5 worker job-type constants (`report.run`, export, `report.deliver`, `schedule.run`, dashboard refresh), 4 roles (privileged = admin + developer).
- graph-backbone/schedules-delivery.md: 24 routes (10 personal incl. 2 history pages, 14 master/company incl. 4 lookups), 4 TS files, 8 scheduling modules, 9 delivery modules, 3 precious tables (`schedules`, `master_schedules`, `schedule_runs`).
- Source read in full: `web/blueprints/schedules.py` (1222), `web/scheduling/{runner,tick,cadence,catchup,jobs,personal_views,company_layouts,sabbath}.py`, `web/delivery/{service,email,jobs,filename_template,sharepoint,onedrive,graph_upload,graph_mail,graph_errors,layout}.py`. Repo file `web/data/repositories/schedules.py` sampled by symbol list only.

## Extra codegraph queries I would have run

`codegraph impact _as_str_list`, `codegraph callers split_recipients`, `codegraph callers convert_personal_schedules`, `codegraph callees ScheduleRunner.run`, `codegraph impact _DELIVERY_PARAM_KEYS`, `codegraph node web/data/repositories/schedules.py`.

## What's wrong / messy (ranked)

### God file + mixed concerns

1. `web/blueprints/schedules.py` is 1222 lines, one blueprint, two products (personal and company/master) plus presentation helpers (`_params_label`, `_PERIOD_OPTIONS`, `_STATUS_OPTIONS`, `_MASTER_REPORT_FILTERS`) and validation logic (`_normalize_master_params`, `_load_schedulable_view`). Natural seam already exists at the `# --- master schedules (admin)` comment (line 780). Split candidate: `schedules_personal.py` / `schedules_master.py` / `schedule_params.py`.
2. `web/static_src/js/master_wizard.ts` is 1117 lines (>500 threshold). `personal_wizard.ts` is 551.
3. `web/scheduling/runner.py` is 779 lines; `ScheduleRunner.run` (lines 111–222) carries Sabbath skip, re-auth, test-mode, catch-up windows, retry bookkeeping, and run-row recording in one method. `_run_master_fanout` (444–554) re-implements outcome merging that `_combine_outcomes` (698–728) also does.

### Duplicated logic

4. `_as_str_list` and `_as_bool` are defined twice, byte-identical: `blueprints/schedules.py:839–862` and `scheduling/runner.py:631–649`. `company_layouts.py:87–102` has a third variant split into `_status_list` / `_salesman_list`.
5. `_DELIVERY_PARAM_KEYS` exists in two places with different membership: blueprint (5 keys, line 180) vs runner (9 keys, line 569). The blueprint set is missing `split_by_salesman`, `email_to_salesmen`, `email_salesman_keys`, `skip_sabbath`. Schema drift risk: an update through `PUT /api/schedules/<id>` re-applies view params but only strips the smaller set.
6. `DeliveryResult` merge block appears twice: `runner._run_master_fanout` lines 535–554 and `runner._combine_outcomes` lines 707–728 (same 12 fields, same `next(...)` idiom).
7. Empty-data mail decision (`no_data_all`, `no_data_me`, `test_empty`, `empty_to_test`, `empty_recipients_override`) is computed identically in `_deliver_window` (326–346) and `_run_master_fanout` (460–480).
8. Token fetch + `_mock_or_raise` + `_ensure_folder` + `_MOCK_TREE` + `list_folders` shape duplicated between `SharePointService` and `OneDriveService` (`sharepoint.py:60–231`, `onedrive.py:36–149`). `onedrive.py` imports the private `_validate_segments` from `sharepoint.py`.
9. `create_schedule` (511–562) has two near-identical branches (Default vs saved view); lines 523–540 and 545–562 differ only in `report_key/params/layout/view_name` source.
10. `AppSettingsRepository` is imported inline three times in the blueprint (lines 87, 390, 1001) even though `_settings()` already wraps it.
11. Master-schedule 404 + `_require_master_edit` preamble repeated verbatim in `copy_master`, `update_master`, `toggle_master`, `delete_master`, `run_master` (5 sites). Personal side has `_personal_or_404`; master side lacks the equivalent helper.

### Inconsistent patterns

12. Folder-path semantics overloaded: column `sharepoint_path` stores either a SharePoint path or a OneDrive path, disambiguated by `params["folder_kind"]`, with a fallback to `is_shared` for older master rows (`runner._onedrive_user` 576–592). Three helpers negotiate it on write: `_check_sharepoint`, `_check_personal_folder`, `_master_folder`, `_personal_folder_and_kind`. Body accepts both `onedrive_path` and `sharepoint_path` keys.
13. `_parse_is_shared` accepts both `is_shared` and `share` request keys; default `True` when absent means a PUT without the key silently flips a private schedule to shared.
14. Recipient validation diverges: master uses `_clean_recipients` (aborts on invalid), personal uses `_recipients_for_view_schedule` (silently drops invalid extras via `split_recipients`).
15. Owner lookup: `runner._owner` (392–397) runs a raw `SELECT * FROM users WHERE id=?` with a stale comment "UserRepository has get_by_email; fetch by id via a tiny direct query" -- `UserRepository.get_by_id` exists (`users.py:92`) and the blueprint uses it.
16. `run_and_deliver` has 16 keyword parameters; 4 call sites (`delivery/jobs.py:34`, `runner.py:330/464/500`) each pass a different subset. `_deliver_window` takes 15 keywords.
17. `getattr(sched, "filename_template", "")` / `getattr(sched, "view_name", None)` / `getattr(sched, "name", "")` defensive getattr on dataclasses that already define those fields (repeated ~20× across blueprint + runner). Either the dataclasses are the contract or they are not.
18. Cadence time-parse fallback: `_parse_time` silently coerces garbage to `08:00` on both `normalize` (write) and `due_now` (read). A malformed stored time never surfaces.
19. `filename_template.py` and `cadence.py` each define their own `_EASTERN` ZoneInfo; `cadence.py` wraps it in a try/except fallback to UTC, `filename_template.py` does not.
20. Subject stamp in `runner._subject` uses UTC date (`datetime.now(timezone.utc)`), while filename tokens and cadence use Eastern. A 9pm Eastern send gets tomorrow's date in the subject.

### Dead / orphan / unreachable

21. `skip_sabbath` param is read by `sabbath.skip_sabbath_enabled` and stripped by runner, but no blueprint, wizard TS, or template writes it (rg over `web/blueprints/schedules.py`, `web/static_src/js/*.ts`, `web/templates/*.html` → 0 hits). Only settable by hand-editing JSON.
22. `personal_views.convert_personal_schedules` + `_already_backed_by_view` + `_imported_view_name` + `_recipients_for_owner` + `_normalize_recipients` (lines 37–119) are a one-time migration living in a runtime module; caller is `web/data/migrate.py`. Same file mixes the hot-path predicates `is_custom_date_params` / `is_schedulable_saved_view`.
23. `GET /master-schedules` is a pure redirect to `/settings/company-schedules` (blueprint 1017–1022). `master_schedules.html` (434 lines) is only reached via `{% include %}` from `company_schedules.html:70`.
24. `_recent_run_log` accepts `viewer=` and never reads it (line 434–435; passed at 497).
25. `_MASTER_REPORT_FILTERS` comment says "Same filter keys the report viewer uses. Kept here (not imported from the reports blueprint)" -- a hand-maintained copy of registry data with no test that it matches the report specs.
26. `email.py` module docstring (lines 1–15) still narrates a past incident ("that was the Friday 'success with no email' failure mode"); `_record` comments do the same (352–366). History belongs in DECISION-LOG, not code.
27. `sharepoint._resolve_drive_id` falls back to `GET /sites?search=achim` (line 191) -- tenant name hardcoded in library code.

### Error handling

28. `email.deliver` returns `DeliveryResult(ok=False)` on Graph/SMTP failure but raises nothing; `runner._deliver_window` re-raises based on `_inbox_already_got_mail`. Two layers negotiating "was it really a failure" via string channel names (`"graph"`, `"smtp"`, `"outbox"`, `"mixed"`, `""`).
29. `email._record` status logic (lines 357–373) has four booleans (`sp_requested`, `mail_went_out`, `email_delivered`, `ok`) deriving `status` ∈ {sent, outbox, failed}; comments explain a retry-duplicate bug instead of the rule.
30. `sabbath.melacha_assur` fails open with a module-level unbounded `_cache` dict keyed by date window; never evicted for the life of the process.

### Naming

31. `MASTER` / "master schedules" in code vs "Company schedules" in UI and history labels (`kind = "Company"`). Routes use `master-schedules`, page title says company.
32. `sent_via_smtp` on `DeliveryResult` means "Graph or SMTP transmitted" (comment admits legacy name). Serialized into `schedule_runs.output_meta` as `sent_smtp`.
33. `_uid(email)` is called per request and again inside helpers (`_has_schedulable_views`, `_viewer_run_log`, `_load_schedulable_view`) -- repeated DB round-trips for the same principal.

## Coverage skeleton (names/paths only)

### Routes (24, all `@require_login`)

Personal: `schedules_page`, `recent_runs`, `create_schedule`, `update_schedule`, `toggle_schedule`, `delete_schedule`, `run_schedule`, `copy_schedule`, `list_schedulable_views`, `schedule_history`
Master: `master_history`, `company_schedules_page`, `master_page` (redirect), `master_lookup_status`, `master_lookup_salesmen`, `master_lookup_salesmen_emails`, `master_lookup_customers`, `create_master`, `copy_master`, `update_master`, `toggle_master`, `delete_master`, `run_master`

### Modules

- `web/blueprints/schedules.py`
- `web/scheduling/runner.py` (`ScheduleRunner`, `_run_master_fanout`, `_combine_outcomes`, `_summary_message`, `flush_pending_fail_notices`)
- `web/scheduling/tick.py` (`enqueue_due`, `hold_until_next_slot`, `make_tick`, `_consider`, `_within_window`)
- `web/scheduling/cadence.py` (`normalize`, `describe`, `due_now`, `clock_ready`, `day_matches_date`, `next_matching_date`, `later_iso`)
- `web/scheduling/catchup.py` (`classify_action`, `makeup_due`, `overlay_windows`, `run_param_windows`)
- `web/scheduling/sabbath.py` (`skip_sabbath_enabled`, `melacha_assur`, `_assur_from_items`)
- `web/scheduling/jobs.py` (`enqueue_schedule_run`, `make_schedule_run_handler`)
- `web/scheduling/personal_views.py` (`is_custom_date_params`, `is_schedulable_saved_view`, `convert_personal_schedules`)
- `web/scheduling/company_layouts.py` (`seed_canonical_company_views`, `stamp_company_views_on_schedules`, `is_daily_company_ordered`, `is_heshy_open_orders`, `params_without_window`)
- `web/delivery/service.py` (`DeliveryService.run_and_deliver`, `send_no_data_notice`)
- `web/delivery/email.py` (`EmailService.deliver`, `send_notice`, `_graph_send`, `_maybe_folder`, `_record`, `split_recipients`, `_email_bodies`)
- `web/delivery/jobs.py` (`enqueue_delivery`, `make_delivery_handler`)
- `web/delivery/filename_template.py` (`resolve_filename_template`, `resolve_folder_template`, `token_values`, `TOKEN_HELP`)
- `web/delivery/sharepoint.py` (`SharePointService`, `strip_reports_home`, `_validate_segments`, `TEST_SHAREPOINT_FOLDER`)
- `web/delivery/onedrive.py` (`OneDriveService`, `onedrive_children_url`)
- `web/delivery/graph_upload.py` (`upload_drive_item`, `resolve_web_url`)
- `web/delivery/graph_mail.py` (`GraphMailer.send`, `GraphMailError`)
- `web/delivery/graph_errors.py` (`graph_error_message`)
- `web/delivery/layout.py` (`expand_clones`, `apply_layout`, `_filter_rows`, `_sort_rows`)
- `web/data/repositories/schedules.py` (`ScheduleRepository`, `MasterScheduleRepository`, `ScheduleRunRepository`, `next_copy_name`; 568 lines, not read in full)

### Templates / TS

`schedules.html`, `personal_schedule_wizard.html`, `company_schedules.html` → includes `master_schedules.html`, `schedule_history.html`; (`schedule_runs.html` belongs to settings blueprint)
`web/static_src/js/schedules.ts`, `personal_wizard.ts`, `master_wizard.ts`, `filename_preview.ts`

### Tables

`schedules`, `master_schedules`, `schedule_runs`, `outbox` (written by `EmailService._record`), `company_views` (read by runner `_layout_for`), `saved_reports` (personal view source), `app_settings` (test mode, seed skip names)

### Existing tests (129 functions)

`tests/test_scheduling.py` (42), `test_delivery.py` (39), `test_catchup.py` (12), `test_repositories_delivery.py` (11), `test_filename_template.py` (9), `test_schedule_seed.py` (8), `test_sabbath.py` (6), `test_graph_errors.py` (2). Plus `test_blueprints.py` covers `convert_personal_schedules`.

Gaps observed by name only (not verified by running): no test file named for `tick.py` hold/claim slot, `company_layouts.py` stamping, `layout.py` filters, `graph_upload.py` chunking, or the `_DELIVERY_PARAM_KEYS` drift between blueprint and runner.
