# Testing Strategy

Testing plan built alongside code. Each feature/module gets an entry documenting what to test, expected behavior, and edge cases. See `testing-protocol.mdc` for rules.

A cheaper model can use this file as a guide to run the full test suite without deep context.

---

## Phase 9 report parity and hygiene (2026-09-01)

**What to test:**
- Built web reports are the eight retained keys; Customer Aging stays BACKLOG (`test_phase9_parity.py`).
- Ordered Summary includes `CustomerAccount`. Invoiced commission fraction/per-invoice rate tests stay in `test_report_invoiced.py`. Number 4 YTD tabs stay in `test_report_number_4.py`.
- No in-app email-distribution module under `v3/`.
- Artifact allowlist includes `tools/supervise-web.sh` (App Service boot). Generated `v3/web/static_dist/` matches `npm run build` including vendor/help files.

**Expected behavior:**
- Parity matrix in `REPORT-PARITY.md` matches the registry.
- `pip install --require-hashes -r requirements.txt` is the Production and CI set (`requirements.in` is the range source). The lock must pin `exceptiongroup` and `tomli` so Python 3.10 pytest extras are hashed.

**Test files:** `v3/tests/test_phase9_parity.py`, existing `v3/tests/test_report_*.py`

---

## Phase 8 UI/accessibility (2026-09-01)

**What to test:**
- `openDialog` is used by admin, SharePoint, login, Customer Last Order, and report email. Background gets `inert`. Reduced-motion scroll uses `auto`. Hidden-tab pollers reschedule on `visibilitychange` (`dialog.ts`, page modules).
- Email-now timeout copy does not say “check the outbox” (`report-delivery.ts`).
- Missing `from_report` draft shows an error on Schedules; blocked sessionStorage does not navigate (`master_wizard.ts`, `report-delivery.ts`).
- Tabulator MIT text is vendored and linked from Settings (`TABULATOR-LICENSE.txt`).
- Source checks in `test_phase8_a11y.py`. Browser matrix (roles, widths, themes, flows) is the phase gate, not this file.
- Dark theme uses `--primary` for text (`#60a5fa`) and `--primary-fill` (`#2563eb`) for filled buttons so white labels stay ≥4.5:1. Commission card headers stay `#1a5a94` on white text. Filter/close leftovers are 44px (`col-filter-btn`, `group-pill-x`).
- Light text `--primary` is `#1d4ed8` so chips/status on `--primary-light` stay ≥4.5:1; fill stays `#2563eb`. Light success/error/warning and dark error tokens are the darker/lighter values that pass on their tint surfaces. Admin `api()` turns a dropped network request into a 503 JSON error so Add user still announces.
- Monochrome-dark `--primary` is light zinc (`#d4d4d8`) on cards; `--primary-fill` stays `#52525b`. Done/failed report-job fabs use darker greens/reds (`#15803d` / `#b91c1c`, with dark-theme overrides) so white labels stay ≥4.5:1.
- Export/More `bindMenu` closes on Tab as well as Escape and returns focus to the button. Report-page customer picker Arrow/Enter/Escape matches `SearchablePicker`.
- Shell notification and recent-job pollers use `watchHiddenPoll`. Lookup polling no longer writes the unused `lookupPollTimer` sentinel. Dashboard live region resets `role` to `status` when cleared.
- Missing `from_report` draft calls `openWizard()` then `masterMsg` so the alert is not trapped in a hidden wizard.
- Customer Last Order pick-page lookup retries use `watchHiddenPoll` in `customer_last_order.ts`.

**Expected behavior:**
- Dialogs trap focus, Escape closes, opener is restored.
- Admin/dashboard tables scroll inside `.table-scroll` at 320px.
- Settings/dashboard save failures announce in a live region.
- Light/dark/monochrome/monochrome-dark body text, primary-on-card, primary buttons, and done/failed job fabs meet 4.5:1.
- Menu Tab/Escape returns to the opener. Report customer picker Arrow/Enter/Escape matches the schedule picker.

**Test files:** `v3/tests/test_phase8_a11y.py`

---

## Phase 7 one-site persistence (2026-09-01)

**What to test:**
- Home-site config prefers `SITE_PRECIOUS_DB_PATH` over `BETA_PRECIOUS_DB_PATH`. BETA still works when SITE is unset. Prod home requires an explicit SITE/BETA path and `LITESTREAM_AZURE_SITE_PATH` or `LITESTREAM_AZURE_BETA_PATH`. `LITESTREAM_AZURE_PATH` / `PRECIOUS_DB_PATH` are not enough (`test_config.py`).
- `startup.sh` refuses prod boot when the serving path is missing, on `/home`, replica settings are missing, Litestream is missing, restore leaves an empty/zero-byte/corrupt file, or integrity (`users` >= 1) fails. BETA alias restores only that file, not `PRECIOUS_DB_PATH` (`tests/test_startup_restore.py`). Restore-preflight runs this file with `--noconftest`.
- Before migrate: missing/zero-byte/corrupt/no-users fail. After migrate: required tables, latest schema, `site_db_role=home`. A sqlite stopped at 0015 with one user migrates through 0016+ (`test_precious_integrity.py`).
- Prod bootstrap refuses empty/schema-only DBs and writes `.bootstrap-failed`. A restored user row boots and sets the sentinel (`test_process_ownership.py`).
- Prod `/readyz` is 503 for missing, zero-byte, or corrupt sqlite. JSON stays `{status: not_ready}` (`test_smoke.py`). Live Azure empty-disk drill is not in CI.

**Expected behavior:**
- One serving sqlite and one Blob replica. Empty/corrupt/stale files never become a fresh Production site.
- `is_beta=True` and the `session` cookie stay.

**Test files:** `v3/tests/test_config.py`, `v3/tests/test_precious_integrity.py`, `v3/tests/test_process_ownership.py`, `v3/tests/test_smoke.py`, `tests/test_startup_restore.py`

---

## Phase 6 report and schedule defects (2026-08-31)

**What to test:**
- Commission cards use the current bucket's salesman number. SP `commission` is a fraction (`1` = 100%; values above 1 are percents). Invoice SP `0` stays $0. Commissions tab % still shows leftover `salesmen.commission_pct`. The no-YTD fallback uses each invoice's own rate and the same customer/salesman grouping as the summary (`test_report_invoiced.py`).
- Custom interval start after end is rejected (`test_dates.py`, `test_run_invalid_custom_dates_returns_400`).
- Company save with Sabbath skip unchecked persists `skip_sabbath=false` (`test_master_schedule_persists_skip_sabbath_false`).
- Forward `0026` marks leftover `scheduled` rows `legacy`. `last_run_at` ignores `manual`/`legacy`/`unknown` so a deploy-day historical row does not eat the next clock slot (`test_last_run_at_ignores_legacy_trigger`).
- Kept-run result/export is denied after `kept_until`. Expired kept payloads prune; the expired `kept_until` stays as a tombstone so later cache hits cannot revive that job (`test_expired_kept_run_is_not_served`, `test_prune_expired_kept_drops_payload`, `test_job_prune_skips_queued_and_live_kept`). Personal run history 30 days, master 90 (`test_schedule_run_prune_personal_30_master_90`). Tick calls job + run prune (`test_tick_prunes_cache_exports_and_fails_hung`).
- Configured `SP_SITE_URL` that does not resolve raises; no `sites?search=` fallback (`test_configured_site_url_does_not_search_on_failure`). Empty URL may still search.
- View-only manager can company Send now; copy/edit stays tighter (`test_view_only_manager_can_company_send_now`).
- Reconcile diagnostics and `claim-once` are POST+CSRF for developers. GET is 405. Query-string `DIAG_RECONCILE_KEY` is gone (`test_diagnostics.py`).
- `@achimonline.com` (and subdomains) send. Other domains are stored, noted pending, and blocked until admin/developer approve. CC/BCC on a schedule are noted too (`test_schedule_save_notes_pending_cc_and_bcc`). Settings test emails stay sendable. `send_notice` is not filtered (`test_email_now_pending_external_needs_approval`, `test_settings_approve_external_then_email_now_sends`, `test_salesman_cannot_approve_external`, `test_manager_cannot_approve_external`, `test_send_notice_is_not_filtered`).

**Expected behavior:**
- Business outputs match Q1–Q3 and Q8–Q10.
- Unapproved outside-company addresses never receive mail.
- Opening an expired kept run does not serve `kept_run_payloads` and does not fall through to ordinary cache.

**Test files:** `v3/tests/test_report_invoiced.py`, `v3/tests/test_dates.py`, `v3/tests/test_blueprints.py`, `v3/tests/test_repositories_delivery.py`, `v3/tests/test_jobs.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_delivery.py`, `v3/tests/test_diagnostics.py`

---

## Phase 5 delivery recovery (2026-08-31)

**What to test:**
- Leftover `pending` is migrated by 0023 on a pre-0023 schema (`test_pending_migrates_to_unknown`). Forward `0024` stores `slot_when` on the leg.
- Clock enqueue freezes `slot_id`, `slot_day`, and `slot_when`. Execution does not key legs off `eastern_date_iso()` (`test_enqueue_freezes_slot_day`, `test_slot_id_does_not_use_execution_day`, `test_parse_frozen_when_prefers_iso_over_day`). Operator retry after the job row is gone copies `slot_when` from the leg (`test_operator_retry_parses_clock_slot_when_job_is_gone`). Pre-0024 empty legs fall back to midnight Eastern of `slot_day` (`test_job_gone_retry_empty_slot_when_uses_midnight_eastern`).
- Crash before send (prepared) is failed/retryable. Crash while sending email is unknown and not auto-retried. Crash after Graph accepted commits sent (`test_crash_before_external_call_is_retryable`, `test_crash_while_sending_email_is_unknown_not_retried`, `test_crash_after_graph_accepted_commits_sent`). Worker death still cancels `schedule.run` / `report.deliver`. Child timeout and nonzero unsafe child exit settle sending email legs to unknown (`test_child_timeout_settles_sending_email_unknown`, `test_nonzero_child_exit_settles_sending_email_unknown`).
- Graph timeout after submit raises `GraphUnknownError`. Connection refused is a plain `GraphMailError`. sendMail 401 clears the token and retries once. EmailService records `unknown` (`test_graph_timeout_after_submit_is_unknown`, `test_graph_connection_refused_is_failed_not_unknown`, `test_graph_401_clears_token_and_retries_once`, `test_email_deliver_records_unknown`).
- Empty skip does not insert a sent workbook-email leg. A failed no-data notice stays failed/retryable. Already-settled email+folder skip does not crash (`test_empty_skip_does_not_mark_workbook_email_sent`, `test_failed_notice_stays_failed_and_retryable`, `test_already_settled_email_skip_does_not_crash`).
- Partial fan-out: a sent salesman stays sent while a failed one retries (`test_partial_fan_out_keeps_sent_and_failed`).
- Operator mark-sent and reopen-for-retry (`test_operator_mark_sent_and_retry`). Retry reuses the frozen `slot_id` so attempt_key matches (`test_operator_retry_reuses_frozen_slot_after_midnight`, `test_operator_retry_parses_clock_slot_when_job_is_gone`). Privileged-only History POST (`test_reconcile_retry_http_reuses_slot_and_rejects_salesman`). Retry sends only that attempt and the stored target (`test_retry_sends_only_the_selected_attempt_and_frozen_target`). Fan-out retry uses the stored salesman address when the live email is blank, the salesman was dropped, or that salesman was the last live key (`test_fanout_retry_sends_stored_target_when_live_email_blank`, `test_fanout_retry_sends_stored_target_when_salesman_dropped`, `test_fanout_retry_sends_when_last_live_key_removed`). A stored full email retry still sends after the live schedule becomes split-only (`test_full_leg_retry_sends_when_schedule_becomes_split_only`). Two selected legs on one slot get two jobs (`test_reconcile_retry_two_legs_same_slot_queues_two_jobs`). A later period edit still sends the selected leg (`test_retry_after_period_change_still_sends_selected_leg`). Email-now unknown alerts include `attempt_key`; privileged `/schedules` lists unattached unknown legs (`test_email_now_unknown_alert_includes_attempt_key`, `test_schedules_page_lists_unattached_unknown_for_admin_not_salesman`).
- Crash after folder Graph acceptance commits sent; interrupted folder upload is failed/retryable; GET verify after a lost PUT marks sent (`test_crash_after_folder_accepted_commits_sent`, `test_crash_while_folder_sending_is_failed_retryable`, `test_folder_upload_error_then_get_is_sent`). Restart verify uses the enqueue clock (`test_folder_verify_uses_frozen_when_not_live_clock`). Job-gone retry GET still uses the frozen `{HH}{mm}` name (`test_job_gone_retry_folder_keeps_frozen_filename`). A later filename-template edit still GET-verifies the stored name (`test_retry_after_filename_template_change_gets_original_name`). Reopen keeps the upload session URL (`test_reopen_for_retry_keeps_upload_session`).
- Upload session resumes from `nextExpectedRanges` (`test_upload_session_resumes_from_next_expected_range`). Graph 429 Retry-After still holds.
- Token cache refreshes 60s before expiry (`test_graph_token_refreshes_before_expiry`).
- Cancel after build before send does not create a sending leg; cancel during send marks failed, not sent (`test_cancel_after_build_before_send_does_not_create_sending_leg`, `test_cancel_during_send_marks_failed_not_sent`). Existing cancel-after-workbook / cancel-no-data-notice tests still apply.
- Legs older than 90 days prune (`test_legs_prune_old_rows`). Tick calls `DeliveryLegRepository.prune`.

**Expected behavior:**
- A required email that definitely did not send is never recorded success.
- Graph connection loss after submit is unknown: no auto-retry; operator confirms from History or (email-now) Schedules.

**Test files:** `v3/tests/test_delivery_recovery.py`, `v3/tests/test_delivery.py`, `v3/tests/test_graph_mail.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_jobs.py`

---

## Phase 4 process ownership (2026-08-31)

**What to test:**
- `create_app` / Gunicorn `wsgi.py` start no job poller, scheduler, bootstrap thread, or `v3-lookups` thread.
- `flask bootstrap` / `python -m web.bootstrap` migrates and seeds and does not start the worker.
- The worker process claims a job. `python -m web.jobs.child JOB_ID` runs an already-claimed row.
- A child timeout kills the process group, records `cancelled`, and a later job can still run (`test_child_timeout_cancels_and_kills`, `test_two_hung_children_do_not_stop_the_queue`).
- Worker crash recovery requeues safe jobs under the retry cap (`test_orphaned_running_job_is_recovered`, `test_repeatedly_crashing_job_is_failed_not_looped`) and cancels `schedule.run` / `report.deliver` even when `attempts` is already at the cap (`test_recover_orphans_cancels_delivery_not_requeued`, `test_recover_orphans_cancels_schedule_run_not_requeued`, `test_recover_orphans_cancels_delivery_at_retry_cap`, `test_recover_orphans_cancels_schedule_run_at_retry_cap`). SIGTERM/stop kills the child but leaves the row `running` so that recovery can run (`test_worker_stop_leaves_safe_job_running_for_recovery`, `test_worker_stop_lets_recover_cancel_in_flight_delivery`). A child that exits nonzero on its own still fails for safe types and cancels `schedule.run` / `report.deliver` (`test_nonzero_child_exit_still_fails_when_worker_is_not_stopping`, `test_nonzero_child_exit_cancels_delivery_not_failed`).
- While a child `wait` is blocking, the worker still writes `worker_heartbeat` (`test_worker_heartbeat_stays_fresh_while_child_wait_blocks`).
- Scheduler `start()` failure raises out of `run_worker` (`test_scheduler_start_failure_stops_the_worker`).
- `tools/supervise-web.sh` runs bootstrap first; if either Gunicorn or the worker exits, the other is stopped (`tests/test_supervise_web.py`).
- Prod `/readyz` is 503 when worker/scheduler heartbeats are missing or stale; `/healthz` stays 200. Dev `/readyz` stays 200 without heartbeats. `.bootstrap-failed` still 503.
- `claim_next` prefers `schedule.run` over interactive exports. Interactive enqueue is 503 when the queue is deeper than 40 or the oldest queued job is older than 20 minutes; `schedule.run` is exempt.
- HTTP lookup `status()` does not start a thread. Home-site dropdowns read the sqlite customer mirror; the worker cron `lookups.refresh` fills it when the dashboard UI is off.

**Expected behavior:**
- Flask/Gunicorn only serve HTTP and enqueue/read durable state.
- A timed-out report actually stops (child killed), not only a DB row flip.
- A killed worker cannot leave prod `/readyz` green.

**Test files:** `v3/tests/test_process_ownership.py`, `v3/tests/test_jobs.py`, `v3/tests/test_smoke.py`, `tests/test_supervise_web.py`, `v3/tests/test_dashboard_mirror.py`

---

## Phase 1.1 production deploy workflow (2026-08-28)

**What to test:**
- Every Azure deploy job has `if: github.ref == 'refs/heads/webapp-cache'` so `workflow_dispatch` from another branch does not package or deploy.
- `build` needs tracked-secrets, gitleaks, semgrep, zizmor, python, frontend, and restore-preflight. `deploy` needs `build`.
- Restore preflight runs `tests/test_startup_restore.py --noconftest`.
- Python job is full v3 pytest plus root pytest.
- Deploy job `environment` is `production`.

**Expected behavior:**
- A failed check job prevents the artifact and the Azure Production deploy.
- This PR does not run the Azure workflow (push filter is `webapp-cache`); zizmor on CI lints the YAML.

**Test files:** `.github/workflows/webapp-cache_achim-sales-reports.yml`, `tests/test_startup_restore.py`

---

## Phase 2 auth (single identity store)

**What to test:**
- A leftover Live `session["user"]` cookie does not sign anyone in, does not create a user, and does not skip DB role refresh.
- `/dev/role-picker` GET/POST require live `authz.actor_is_developer` (real actor during impersonation). `p.is_dev` and admin are not enough. Demoted developer is 403 (or signed out).
- MSAL `/auth/callback` uses `get_by_email`, not `upsert`. Unknown and inactive Entra users get 403 "Not authorized" and no new/reactivated row.
- `bootstrap_background` does not call `seed_users_from_live`. `flask import-live-users` writes `app_settings.live_user_import` with path, imported user count, and imported grant count. A missing Live DB file or a SQLite file without `app_users` exits non-zero and does not write the marker. An empty valid `app_users` table may record users=0.
- Magic-link tokens are SHA-256 at rest (`token_hash` PK). Consume is one atomic hash update. Access-log filter redacts `/login/magic-link/<token>`. Tick prunes attempts/tokens at 90 days.
- `POST /login/magic-link` with `X-Forwarded-For: 1.2.3.4, 9.9.9.9` records `9.9.9.9` (ProxyFix, one Azure hop), not the leftmost spoofed IP.
- A session cookie signed with the previous Flask secret does not stay signed in.
- `next=/\evil.com` and `next=/%5Cevil.com` are not kept for post-login redirect (`login_redirect` and `/login/start`).
- An admin POSTing `/impersonate` targeting a developer gets 403 and keeps their own session. A developer can still impersonate a developer.
- MSAL token exceptions and Entra `error_description` are not copied into the `/auth/callback` 400 body or into logs (logs may include the error code only).

**Expected behavior:**
- One identity store: precious `users`. Cookie/session fields never grant roles.
- Boot does not read `/home/data/app.db`. `LIVE_DB_PATH` remains for the CLI until import evidence exists.

**Test files:** `v3/tests/test_auth.py`, `v3/tests/test_magic_link.py`, `v3/tests/test_session_authz.py`, `v3/tests/test_seed_users_grants.py`, `v3/tests/test_scheduling.py`

---

## Phase 3 SQL-only v3

**What to test:**
- `ReportService.builder_for` always uses the SQL orchestrator (Item Averages calls `item_customer_sales_rolling_12`).
- Cache/dedup keys do not take an origin token.
- Settings has no Report data sources picker. `GET /api/dev/beta-sources` is 404.
- `v3/web` does not import `reports.*` CLI runners. A tree walk under `v3/` finds no D365 OData mentions except frozen migration `0016_report_sources.sql` and Graph `@odata.type`.
- Scoped salesman keys apply to every tab of Ordered, Invoiced, Salesman, Number 4, and Customer Activity. Item Averages stays privileged SQL. Sales by State stays company-wide (all three tabs). Customer's Last Order already has in-app scope tests.

**Expected behavior:**
- Every visible web report uses the Reporting API. Missing SQL fails the run. CLI/Automation OData stays under `reports/`, `core/`, `data/`, `runbooks/`.

**Test files:** `v3/tests/test_v3_sql_only.py`, `v3/tests/test_report_service.py`, `v3/tests/test_blueprints.py`

---

## Sol list leftovers (2026-08-28)

**What to test:**
- Custom dates raise; commission `1` is 1%; monthly commission uses each month's rate; Ordered Summary groups by CustomerAccount; Hebcal failure skips send.
- Keep this run stores a precious snapshot; cache prune does not drop it; tick prunes cache/exports and cancels jobs running > 45 minutes.
- Graph 429 honors Retry-After (`test_graph_send_retries_429_then_succeeds` asserts the delay; `test_upload_session_retries_429` same for upload sessions).
- Manual Send now does not consume the scheduled slot (`test_last_run_at_ignores_manual_trigger`). Catch-up clears only after success; stays after failure/cancel. Schedule history uses payload `row_count`. Tick prune + hung-job cap (`test_tick_prunes_cache_exports_and_fails_hung`).
- `POST /api/reports/<key>/run` returns 400 for invalid custom dates (`test_run_invalid_custom_dates_returns_400`). Cancel after cache put drops the row (`test_cancel_after_put_drops_cache`).
- Bad Litestream checksum refuses install (`test_prod_bad_litestream_checksum_refuses_boot`).
- Empty-disk prod restore refuses boot (`tests/test_startup_restore.py`). Live Azure drill is not in CI.
- Hung jobs running > 45 minutes are cancelled and are not requeued (`test_fail_hung_cancels_old_running_jobs_not_requeued`). The worker also kills the child on that cap.
- Prod outbox-only delivery is not success (`test_prod_outbox_only_is_not_success`).
- A master schedule with no recipients, folder, or salesman split fails instead of recording success (`test_runner_master_with_no_targets_fails`).
- Demoted users cannot download a finished export that was built wider than their live scope, or an invoiced file that still has the Commissions tab (`test_demoted_admin_cannot_download_unrestricted_export`, `test_demoted_manager_cannot_download_commissions_export`).
- Master exports expire after 90 days (`test_master_exports_expire_after_90_days`).
- Job worker runs handlers with a Flask app context (`test_app_worker_runs_handlers_with_flask_context`).
- Cancel after workbook skips mail (`test_cancel_after_workbook_skips_mail`). Cancelled schedules do not send failure mail (`test_cancelled_schedule_does_not_mail_failure`). Cancel after an empty salesman split does not send the No Data Found notice (`test_cancel_after_empty_split_skips_no_data_notice`).
- `/readyz` is 503 when `.bootstrap-failed` exists (`test_readyz_503_when_bootstrap_failed`).
- Graph upload session POST retries 429 (`test_upload_session_retries_429`).
- `Config.reports_only` tracks `is_beta`. Home copy says Saved views. Report Schedule opens the Schedules wizard.
- CI: full `v3` pytest + root pytest (with `tests/conftest.py`) + `npx tsc --noEmit` + `npm run build` + dist js/css git check.

**Test files:** `v3/tests/test_dates.py`, `v3/tests/test_report_invoiced.py`, `v3/tests/test_report_ordered.py`, `v3/tests/test_sabbath.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_graph_mail.py`, `v3/tests/test_jobs.py`, `v3/tests/test_frontend.py`, `v3/tests/test_config.py`, `tests/test_startup_restore.py`

---

## Single site at / (webapp/ and rebuild/ removed)

**What to test:**
- `PrefixRedirectMiddleware` sends `/beta/reports` to `/reports` and leaves `/login` and `/auth/callback` on the home app.
- Home `/login` links to `/login/start`, not `/legacy`.
- Magic-link tokens: new token invalidates the previous; consume is one-shot; 5/email and 40/IP windows.
- Public origin for emailed links and Entra redirect is `PUBLIC_BASE_URL`, else Azure `https://reports.achimonline.com`, else loopback. Never the request Host.
- Home reports use the SQL Reporting API only. Settings has no data-source picker.
- Base HTML in `is_beta` hides Dashboard and does not show a Beta pill.
- Home HTML has no Test Site nav and no `/test/` href.
- Prod `/static/**.map` is 404; the JS/CSS files themselves stay 200.
- Admin user JSON has no `test_access`; PUT with that key leaves the leftover SQLite column at default.

**Expected behavior:**
- gunicorn `wsgi:application` is v3 only.
- External reps still get a 15-minute one-time link.

**Test files:** `tests/test_wsgi_dispatch.py`, `v3/tests/test_auth.py`, `v3/tests/test_magic_link.py`, `v3/tests/test_public_origin.py`, `v3/tests/test_v3_sql_only.py`, `v3/tests/test_frontend.py`

---

## P0 security containment

**What to test:**
- Scoped salesman keys apply to every tab of SQL reports that have a salesman field. Item Averages stays privileged SQL. Sales by State stays company-wide.
- Prod config rejects missing Litestream Azure account/key/container.
- `/healthz` stays liveness-only; `/readyz` is 503 when prod precious.db is missing.
- `AUTH_MODE=dev` is refused when `APP_ENV=prod`. Legacy `DEV_BYPASS_AUTH` died with `webapp/`.

**Expected behavior:**
- Production boot refuses empty durable state and auth bypass.

**Edge cases:**
- Empty tabs do not require a salesman column.
- `AUTH_MODE=dev` is refused in prod; there is no leftover `DEV_BYPASS_AUTH` switch.
- `/healthz` CSP does not allow unpkg or jsdelivr. Feather, Tabulator JS, and Tabulator CSS are served from `/static/vendor`.

**Test files:** `v3/tests/test_config.py`, `v3/tests/test_smoke.py`. CI and the Azure Production python job run full pytest; restore-preflight is `tests/test_startup_restore.py`.

---

## Review security follow-up (download-file, precious-repair, headers)

**What to test:**
- A workbook in a sibling directory whose name starts with the reports root is rejected.
- An .xlsx under the reports root is served only if that real path is in the current user's history.
- `GET /api/reports/diagnostics/precious-repair?action=delete-ghosts` is 405 and leaves queued jobs. POST with CSRF deletes them. GET `check` still works for developers. Admins get 403.
- `/healthz` includes X-Frame-Options, X-Content-Type-Options, and CSP. HSTS is off in local dev.

**Expected behavior:**
- Logged-in users cannot download another user's Direct Reports xlsx by guessing the path.
- CSRF-exempt GET cannot wipe the jobs table.
- Login and API responses send the browser security headers.

**Edge cases:**
- Non-.xlsx owned files are rejected.
- POST without CSRF token is 400 and does not delete.

**Test files:** `tests/test_download_file_auth.py`, `v3/tests/test_precious_repair.py`, `v3/tests/test_smoke.py`, `tests/test_security_headers.py`

---

## Magic links, history XSS, Excel formula prefix

**What to test:**
- A second magic-link token for the same email consumes the first.
- Consuming a token twice returns None the second time.
- A sixth token create in 15 minutes returns None.
- 40 attempts from one IP trip the IP limit; another IP is unaffected.
- On Azure, emailed links use PUBLIC_BASE_URL or https://reports.achimonline.com.
- Strings starting with `= + - @` get a leading apostrophe; numbers are unchanged.

**Expected behavior:**
- Only the latest unconsumed magic link works. Claim is one UPDATE.
- Consume refuses login if the account is no longer an external salesman (covered in auth; token is still spent).
- History sheet cells are HTML-escaped. Notif diagnostic interpolations use `esc()`.

**Edge cases:**
- Empty IP skips IP throttle.
- Local dev without PUBLIC_BASE_URL emails `http://127.0.0.1:5001/...` (never the request Host).

**Test files:** `tests/test_magic_link.py`, `tests/test_magic_link_origin.py`, `tests/test_excel_formula.py`

---

## Customer access fail-closed

**What to test:**
- Missing dashboard_cache or missing salesman_key is a deny (admin still allowed).
- A salesman matches only their book's sales_group.
- A manager needs a grant for that sales_group and a known book.
- Blank D365 sales_group falls back to cache; a real D365 group can authorize with an empty cache.
- `visible_salesman_keys`: admin unrestricted, manager grants only, salesman own key, salesman without a key is empty.
- Number 4 `make_cell` and salesman `_excel_val` prefix formula leaders.

**Expected behavior:**
- Order-detail and customer-detail do not skip grant checks for managers.
- `/api/customer-addresses`, `/api/customer-price`, and generate-po 403 when the user cannot see the account.
- `/api/customers` does not return the full book to managers or keyless salesmen.

**Edge cases:**
- Last-order may pass D365 `sales_group` when cache is empty.
- Manager `?salesman=` for a key they do not hold returns an empty list.

**Test files:** `tests/test_customer_access.py`, `tests/test_excel_formula.py`

---

## Leftover XSS and Ordered/Invoiced formula prefix

**What to test:**
- Ordered summary cells prefix `=` leaders.
- Invoiced data-sheet cells prefix `=` leaders.

**Expected behavior:**
- Email chips use text nodes, not innerHTML, for the address.
- Order-entry matrix group/color/size/sku strings are escaped.

**Test files:** `tests/test_excel_formula.py`

---

## Legacy CSRF and local Feather

**What to test:**
- POST without a token is 400.
- POST with matching `X-CSRF-Token` or form `csrf_token` is 200.
- Mismatched token is 400. GET is not checked.
- POST `/auth/callback` is exempt (Entra).
- `{% csrf_token %}` renders a hidden `csrf_token` input. Login/dev/role-picker templates use that tag (not an include). Semgrep's Django form rule does not accept the Flask tag, so those form tags carry `nosemgrep`.

**Expected behavior:**
- Fetch wrapper and HTML forms send the session token. Microsoft login callback still works without it.
- Legacy pages load Feather from `/static/vendor`, not unpkg. Report form does not load Chart.js.

**Edge cases:**
- Missing session token is a deny, same as a wrong token.

**Test files:** `tests/test_legacy_csrf.py`

---

## Session role vs DB authorization

**What to test:**
- `Authorization.is_developer` follows the DB role, not the cookie.
- A demoted developer cannot open `/dev/db-explorer` or reporting-api diagnostics; they can still load `/settings`.
- A disabled user is signed out: `/` redirects to login and `/settings/theme` does not stick.
- Impersonating an inactive salesman still loads `/`; db-explorer stays 403.
- Live→v3 user copy drops a revoked salesman key on the next run.
- Legacy `refresh_session_user` rewrites a stale admin cookie to the DB salesman role and drops a deleted user.

**Expected behavior:**
- Session is identity only. Developer tools and privileged nav use the live DB row.
- Inactive own-sessions are logged out. Impersonation continues only while the real actor is an active admin/developer.
- Boot-time live user mirror replaces salesman grants instead of INSERT OR IGNORE.

**Edge cases:**
- Admin cookies cannot open developer diagnostics.
- Users who exist only in the session cookie and not in `app_users` are not a supported login path; `AUTH_MODE=dev` is refused in prod.

**Test files:** `v3/tests/test_session_authz.py`, `v3/tests/test_seed_users_grants.py`, `v3/tests/test_auth.py`, `v3/tests/test_blueprints.py`

---

<!-- Entries are added below as features are built. Each entry follows this format:

## [Feature/Module Name]

**What to test:**
- ...

**Expected behavior:**
- ...

**Edge cases:**
- ...

**Test file:** `tests/test_feature_name.py` (or equivalent)
-->

## Ordered Summary remainder from SP dollar amount

**What to test:**
- Missing `ShippingDollars` shows $0 for Shipping $ and Summary remainder (no qty × price, no Open $ math).
- When the SP sends `ShippingDollars`, Summary Extended Price Remainder and Full Data Shipping $ use that value. Open $ stays Ordered − Shipped − Cancelled.
- `CustomerRequisition` maps to PO #. `ShippingDateRequested` maps to Ship Date.

**Expected behavior:**
- Summary remainder and Shipping $ are ShippingDollars only, summed by customer + item.

**Edge cases:**
- Blank/absent ShippingDollars is 0. Blank ShippingDateRequested does not fail the build.

**Test file:** `v3/tests/test_report_ordered.py`

## Company views (Daily Ordered / Heshy Open Orders)

**What to test:**
- `company_views` upsert rejects Default/Custom; GET presets includes `company`.
- Managers/admins PUT a company view; salesmen GET (`can_edit` false) and 403 on PUT.
- Home page shows a Company views section with `?cview=` links.
- Boot stamps daily company Ordered schedules with Daily Ordered (salesman then customer). Salesman-split and already-named views are left alone. Heshy open-orders (Hkaufman + Open) gets Heshy Open Orders (Full Data only, hide LineNumber, sort customer then order, group by order).
- Send with that view name uses the live company layout even if the schedule snapshot is stale.
- Excel nested groups write banners/totals per level. Sort-then-group keeps customer clusters and does not add a customer total when the only group field is order number.
- Ordered Full Data has CustomerName and ShipDate. Missing SP Ship Date stays blank and still builds.

**Expected behavior:**
- Saved views lists Default, then company views, then personal. Wizard has a Company views optgroup. Schedules View column shows the stamped names.
- Daily Ordered emails group By Customer by salesman then customer. Heshy’s file is one Full Data sheet, customers together, totals per order, no LineNumber.

**Edge cases:**
- Layout `order` listing ShipDate when the column is absent does not fail (`apply_layout` skips unknown fields).
- Nested Excel groups still honour hidden group fields (existing single-group tests).

**Test files:** `v3/tests/test_company_views.py`, `v3/tests/test_blueprints.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_reporting.py`, `v3/tests/test_report_ordered.py`, `v3/tests/test_frontend.py`

## Default view per report

**What to test:**
- GET default-view returns empty Default until someone saves it; PUT stores layout + params.
- Managers/admins can PUT; salesmen can GET (`can_edit` false) and get 403 on PUT.
- Preset list includes `default` plus personal presets. Personal views cannot be named Default.
- New schedule with `view_name=Default` (or empty layout) shows Default on `/schedules`.
- Report-page snapshot (layout with views/order, no view_name) shows Custom.
- Send with Default + empty layout uses the company Default. Default + stored snapshot keeps the snapshot.

**Expected behavior:**
- Wizard first option is Default. Schedules tables have a View column.
- Saved views always lists Default; Edit is managers/admins only; Default cannot be deleted.

**Edge cases:**
- Switching a named view to Default on edit clears the snapshot.
- Staying on Default during edit does not wipe a seeded snapshot.

**Test files:** `v3/tests/test_blueprints.py`, `v3/tests/test_repositories_delivery.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_frontend.py`

## Oversized Graph email: download button

**What to test:**
- Workbooks at/over `MAX_GRAPH_ATTACH_BYTES` are not attached; Graph `xlsx_bytes` is None.
- With a live SharePoint path (test mode off), the file URL is in the plain-text body and in HTML (`Download workbook` button, brand `#2563eb`).
- With no path, the file uploads to `Test` under Direct Reports and the button/link use that URL.
- Company test mode with a live folder (e.g. Invoiced Report/Daily) passes `sharepoint_path=Test`, never the live path. Split legs stay `sharepoint_path=""`.
- If the Test-folder upload fails, the email still sends; delivery is not marked failed.

**Expected behavior:**
- Outlook shows a blue Download workbook button that opens the SharePoint file in `Direct Reports/Test` (test mode) or the live folder (test mode off).
- Plain-text clients still get `Download it here: <url>`.
- Live Daily/YTD/Monthly folders are never written while test mode is on.

**Edge cases:**
- Requested live SharePoint path that fails still fails the whole delivery (unchanged).
- Graph 413 on a small attachment still retries once without the file.

**Test files:** `v3/tests/test_delivery.py`, `v3/tests/test_scheduling.py`

## Number 4: YTD tabs, By Item no money, group by item

**What to test:**
- Both mode builds four tabs (By Customer 12 months + YTD, By Item 12 months + YTD).
- By Item tabs have no money columns; By Customer still has month $ / Total $ / Avg Price / Book Price.
- YTD keeps current-year months only and recalculates Total Qty / Total $ / Avg Price.
- YTD drops rows with no current-year qty or dollars.
- Every tab sets `default_group` to Item #.
- Excel By Item headers are quantity-only.
- Number 4 extra files are not part of the web app.

**Expected behavior:**
- Mode By Item → two qty-only tabs. Mode By Customer → two tabs with dollars. Both → four tabs.
- Grouping starts on Item # until the user changes it.

**Edge cases:**
- Empty view still keeps headers.
- Prior-year-only rows appear on 12 Months and vanish on YTD.

**Test files:** `v3/tests/test_report_number_4.py`, `v3/tests/test_report_service.py`, `tests/test_number_4.py`

## Sales by State (SQL only)

**What to test:**
- Year filter becomes FromDate Jan 1 / ToDate Dec 31 for all three catalog keys.
- Third catalog key is `sales_by_state_filtered` (not `sales_by_state_detail`).
- Summary sorts by sales amount. NYC sales amount appears on the first row only, even if the SP repeats it.
- Detail Excel serial dates become YYYY-MM-DD; negative amounts stay negative.
- Report is built and not a salesman default.

**Expected behavior:**
- Admin reports list shows Sales by State. Salesman inherit list does not.

**Edge cases:**
- Custom period dates override the year window when both start and end are set.

**Test file:** `v3/tests/test_report_sales_by_state.py`, `v3/tests/test_params.py`, `v3/tests/test_report_service.py`, `v3/tests/test_blueprints.py`

## Meeting fixes (tabs, views, groups, empty split, Ordered %, personal Edit)

**What to test:**
- Viewer source has Rename tab, Edit+Delete saved views, subgroup + group pills, clone restore in applyLayout.
- Personal schedules page has Edit and `data-kind="personal"`.
- Split delivery: `email_on_empty=False`; 0-row salesman gets a No Data Found text mail, no xlsx.
- Ordered Full Data, By Customer, By Item, By Order, and By Salesman have Fulfillment % `(QtyOrdered - QtyCancelled) / QtyOrdered`; Summary does not. Grid and Excel color red→yellow→green. skip_by_salesman has no Salesman default_group.
- Daily 9am Salesmen Ordered seed layout omits `by_salesman`.
- Home `?preset=` does not resume the last job for that report (`resumeInFlight` returns false unless `?job=` is also set).
- Saved-views name click calls `loadPreset(p)` (runs). Edit still uses `run: !isReportShown()`.
- A preset with salesman/status keeps those values on the home-card URL and in GET `/api/reports/presets/<id>`.
- Auto-run still sends salesman when the dropdown has not loaded yet (`pendingSalesman` is included in collectParams).

**Expected behavior:**
- Company copy still honours the “email when no data” checkbox.
- Save this view with the same name as the view being edited overwrites it.
- Home preset cards and Saved views → name start a new run with that view’s filters and layout.

**Edge cases:**
- Whole report has rows but one salesman has none → that salesman gets the text mail only.
- Coming back to a report with no `?preset=` still reconnects the last job.

**Test file:** `v3/tests/test_frontend.py`, `v3/tests/test_blueprints.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_delivery.py`, `v3/tests/test_report_ordered.py`, `v3/tests/test_schedule_seed.py`, `v3/tests/test_reporting.py`

## Invoiced salesman from the reporting API (not Excel)

**What to test:**
- Invoiced adapter keeps the SP `SalesGroup` / `salesman` fields as sent.
- When `salesman` is a numeric code (or missing), the customer dropdown source (`customer_master`) supplies SalesGroup.
- A known SalesGroup from the SP does not trigger a customer_master fetch.
- `salesman_map.xlsx` is not used to stamp numbers onto invoiced rows.

**Expected behavior:**
- `salesman=029` + customer 100 assigned to REdwards → Salesman column is REdwards.
- `SalesGroup=REdwards` on the invoice stays REdwards even if the customer master says someone else.

**Edge cases:**
- Numeric salesman with no matching customer keeps the code from the SP.

**Test file:** `v3/tests/test_report_invoiced.py`, `v3/tests/test_report_service.py`

## Home-site schedule failure mail

**What to test:**
- A failed company schedule emails the test-email list even when test mode is off.
- If sending that notice throws, the original schedule error still raises.

**Expected behavior:**
- Subject is `[FAIL] {schedule name}`. Body names company/personal, report, and error.
- Recipients are `settings.test_emails()`, not the schedule's customer list.

**Edge cases:**
- Empty test list: no send, original failure still recorded.
- Fake delivery with no `email.send_notice` (older tests) must not crash.

**Test file:** `v3/tests/test_scheduling.py`

## Home is Beta; Live at /legacy

Superseded 2026-08-27: `webapp/` and extra mounts are gone. See **Single site at /** at the top of this file.

## Login page and developer role picker on home

**What to test:**
- Logged-out `/login` is the Microsoft / External Rep page.
- `/login/start` starts MSAL on this app.
- A developer session can open `/dev/role-picker`, pick a user, then open the picker again.

**Expected behavior:**
- Home login shows "Achim User Login" linking to `/login/start`.
- Role picker lists users; View as Selected User then View as Admin (yourself) both 302 home.

**Test files:** `v3/tests/test_auth.py`, `tests/test_wsgi_dispatch.py`
`

## Company schedules table sorts by name

**What to test:**
- Company list HTML has Apple before Zebra when those two rows exist.
- Table is marked `js-sortable` so column headers can be clicked.

**Expected behavior:**
- Company schedules open sorted by name. Click a header to sort that column.

**Test file:** `v3/tests/test_blueprints.py`

## Deleted company schedules stay deleted

**What to test:**
- Boot seed does not re-insert a company schedule after it was deleted.
- Beta seed no longer includes `Daily 9am` (customer 48999/917/2267).
- Migration `0010` deletes a leftover shared `Daily 9am` row.

**Expected behavior:**
- Delete on company schedules is remembered across deploys/recycles.
- Recreating the same name later is allowed (the skip list is cleared on create).

**Test files:** `v3/tests/test_schedule_seed.py`, `v3/tests/test_blueprints.py`

## Schedules run log starts collapsed

**What to test:**
- After a schedule has run, `/schedules` still renders the Recent run log without the `open` attribute.

**Expected behavior:**
- The log is closed on page load. Run now still opens it so you can watch that job.

**Test file:** `v3/tests/test_blueprints.py`

## Company schedule Copy

**What to test:**
- Copying a company schedule returns 201, a new id, `is_active=False`, and name `{original} (copy)`.
- A second copy of the same source is `{original} (copy 2)`.
- Params, layout, cadence, recipients, SharePoint, filename, share flag, and run-as match the source. Owner is the copier.
- A manager cannot copy a company row they cannot edit (403, no Copy button). They can copy a row they own.
- A salesman cannot copy company schedules (403).
- Personal Copy still leaves the duplicate inactive.

**Expected behavior:**
- Copy on a company row you can edit. The copy stays Off until someone turns it on.
- Shared names stay unique so the copy does not collide with the Azure seed index.

**Edge cases:**
- Copying a 120-character name still fits in the name column (`next_copy_name` truncates the stem).

**Test files:** `v3/tests/test_blueprints.py`, `v3/tests/test_schedule_seed.py`

## Shabbos / Yom Tov schedule skip (Beta clock)

**What to test:**
- Hebcal candle→havdalah window is restricted (Shabbos, or named Yom Tov). Weekday-name candle memo is still Shabbos.
- Check fails open on a malformed Hebcal payload.
- Clock tick during a restricted window records `skipped` and sets `catch_up_pending` + `catch_up_for_date`; no delivery job.
- Skip-class periods (yesterday/daily, mid-month MTD, mid-year YTD) wait for the next regular HH:MM. They do not fire Saturday night after havdalah.
- Reschedule-class periods (last_7_days, last_month, month-end MTD, year-end YTD, salesman/customer_activity) wait until the next Monday–Friday at the same HH:MM.
- MTD skipped on Friday the 30th: Monday 10pm run covers MTD through the 30th, and if that makeup is next month, a second pass through month-end.
- Manual Run now sets `ignore_sabbath` so it still sends.

**Expected behavior:**
- Company and personal clock runs skip Shabbos/Yom Tov (Brooklyn, 18-min candles) and make up at the scheduled clock time, not motzei Shabbos.
- Date windows follow the period: widen yesterday/last_7_days; MTD self-heals in-month; cross-month MTD sends the skipped window plus month-end if needed.
- Run now is a deliberate send and does not skip.

**Test files:** `v3/tests/test_sabbath.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_catchup.py`

## Scheduled Excel matches on-screen tabs

**What to test:**
- A layout `order` list drops server tabs not on that list (Commissions off Salesmen Shipped).
- Empty/missing `order` keeps every tab (old schedules unchanged).
- Saving a company schedule from the wizard with `layout: {}` does not wipe a stored tab order.

**Expected behavior:**
- Right-click → Remove tab, then save/schedule, emails a workbook without that sheet.
- Daily 9am Salesmen Shipped ships without Commissions.

**Edge cases:**
- Optional invoiced tabs (Audit, Totals by Salesman) listed in order but absent from a given run are skipped, not an error.

**Test files:** `v3/tests/test_delivery.py`, `v3/tests/test_blueprints.py`

## Email me + hide Commissions from salesmen

**What to test:**
- Report page has Email me next to Run report.
- Email me POSTs email-now to the signed-in user's address (existing Email modal still works for other people).
- Salesman invoiced run/result/export/email has no `commissions` tab. Admin/manager still have it.
- Page for a salesman sets `data-hide-commissions=1`.

**Expected behavior:**
- One click emails the current filters as Excel to the user. No recipient modal.
- A salesman never sees Commissions on screen or in a file they generate.

**Test files:** `v3/tests/test_blueprints.py`, `v3/tests/test_report_service.py`

## Schedule workbook filenames

**What to test:**
- Blank `filename_template` uses the schedule name plus Eastern date and time, not just the report type.
- Two company schedules on the same report get different filenames.
- Missing schedule name falls back to the report title slug.

**Expected behavior:**
- `Daily 9am` and `DailyOrderReport` no longer both become `Ordered_YYYYMMDD.xlsx`.
- Custom templates still expand tokens as written.

**Test file:** `v3/tests/test_filename_template.py`

## Save and On wait for the next scheduled time

**What to test:**
- Turning a company or personal schedule On after today's time has passed does not enqueue a run.
- Saving an edit on an active schedule does not enqueue a run.
- Creating a schedule whose time already passed today does not enqueue a run.
- A schedule that was already On still catch-up-fires if the slot was missed (app down).
- Turning On before the slot still fires at that time. Run now still sends immediately.

**Expected behavior:**
- Save / On wait for the next cadence. Only Run now or the clock at the scheduled time send.

**Test files:** `v3/tests/test_scheduling.py`, `v3/tests/test_blueprints.py`

## SharePoint folder paths and date tokens

**What to test:**
- Stored paths do not start with `Direct Reports` (that folder is already the drive home). Saving `Direct Reports/Ordered` stores `Ordered`. Nested `Direct Reports/Direct Reports/...` is stripped.
- Folder templates expand the same date tokens as filenames, but keep `/` and spaces (`{Month} {YYYY}` → `August 2026`).
- Customer Activity seed path is `Salesman Report/Customer Activity/{Month} {YYYY}`.
- Migration 0011 strips existing prefixes and sets that Customer Activity month folder when the path is still the old static one.

**Expected behavior:**
- Files land in `Direct Reports/<schedule path>/`, not `Direct Reports/Direct Reports/...`.
- Monthly Customer Activity creates `.../Customer Activity/August 2026` (run date, Eastern).
- Other monthly jobs stay on their current folders until someone adds tokens in the wizard.

**Test files:** `v3/tests/test_filename_template.py`, `v3/tests/test_delivery.py`, `v3/tests/test_schedule_seed.py`, `v3/tests/test_blueprints.py`

## Schedule test mode persistence

**What to test:**
- Shared master schedule names cannot be inserted twice (`IntegrityError`).
- Re-seeding the Azure import does not duplicate rows.

**Expected behavior:**
- Home-site `app_settings` (test mode + emails) survive App Service recycle via the serving Litestream replica (`LITESTREAM_AZURE_SITE_PATH` / `LITESTREAM_AZURE_BETA_PATH` alias).

**Test file:** `v3/tests/test_schedule_seed.py`

## Beta settings hub

**What to test:**
- Salesman `/settings` is `container-narrow`, has You (profile, theme, exclusions), no admin/developer blocks.
- Admin has People, Reports, Delivery, History; not Database explorer.
- Developer has explorer and notification diagnostic.
- `POST /api/admin/report-visibility` hides a report unless a per-user allow override exists.
- Exclusions save without the dashboard blueprint (Beta).
- `/admin/schedule-runs` and `/admin/run-log` are admin-only.
- DB explorer lists precious tables; salesman/admin get 403. No arbitrary SQL.

**Expected behavior:**
- Settings is ~800px, accordion on phone, stacked categories.
- Live Email Distributions is not on Beta.

**Edge cases:**
- Globally disabled report + explicit allow still visible.
- Unknown `report_config` row means enabled.

**Test files:** `v3/tests/test_blueprints.py`, `v3/tests/test_auth.py`

---

## Previously run list + Keep name + OneDrive root URL

**What to test:**
- `onedrive_children_url` at root is `…/drive/root/children`, never `root::/children`. Nested folders keep `root:/{path}:/children`.
- `keep_run` stores `keep_name` and clears name when a Keep overflows the cap of 5 (test uses cap 2).
- `POST /api/reports/runs/<id>/keep` with `{name}` returns that name; `/api/reports/active` includes `keep_name`, `created_at`, `finished_at`.
- Logged-in `base.html` has Recent Reports (`#prevRunsBtn`, styled as a link) and the jobs bar.

**Expected behavior:**
- Header Recent Reports opens the floating list. Keep this run prompts for a name. Chips show Eastern date/time.
- Exporting Excel opens the Recent exports panel. The status line's "Recent exports" words open it again.
- OneDrive Browse at the drive root no longer 400s from a bad Graph path.

**Edge cases:**
- Empty keep name is allowed; UI falls back to the report title. Name is trimmed to 80 chars.

**Test files:** `v3/tests/test_delivery.py`, `v3/tests/test_jobs.py`, `v3/tests/test_blueprints.py`, `v3/tests/test_frontend.py`

---

## Invoiced one-day SQL window (Daily / yesterday)

**What to test:**
- `translate_invoiced` sends `InvoiceDateFrom` at 00:00:00 and `InvoiceDateTo` at 23:59:59.
- `daily` and `yesterday` produce the same window.
- A one-day custom range keeps that day's invoices after the YTD fetch + slice.

**Expected behavior:**
- Scheduled Daily Invoiced is not an empty workbook when that day has invoices.

**Edge cases:**
- Same calendar day From/To must not collapse to midnight–midnight.

**Test files:** `v3/tests/test_params.py`, `v3/tests/test_report_service.py`, `v3/tests/test_dates.py`

---

## Schedule test mode

**What to test:**
- Admin can save several test emails and turn test mode on; cannot turn on with an empty list.
- Salesman cannot POST the API.
- Company schedule Run now in test mode emails only the test list, `[TEST]` subject, SharePoint dumps to `Test` (not the live Daily/YTD folder).
- Split schedules still fan out in test mode; every file goes to the test list with the salesman in the subject/filename.
- Personal schedules ignore test mode.
- Test mode on with no emails fails the run instead of sending to stored recipients.

**Expected behavior:**
- Settings shows the toggle and address chips.
- `/schedules` shows a banner listing the test addresses while On.

**Edge cases:**
- Invalid addresses are dropped; salesman-split jobs still fan out, but every file (full + each salesman) goes to the test list. Salesmen are not emailed.

**Test files:** `v3/tests/test_scheduling.py`, `v3/tests/test_blueprints.py`

---

## Beta import of Live Azure runbook schedules

**What to test:**
- Beta boot inserts Live Azure job names as company master schedules with `is_active=0`.
- Re-seed does not duplicate existing names.
- `amazon_weekly` is not imported.

**Expected behavior:**
- Company schedules list on `/schedules` (home) shows the Live jobs as Off.
- The minute poller does not fire them until someone turns a row On.

**Edge cases:**
- A name you already created on Beta is left as-is (not overwritten).

**Test file:** `v3/tests/test_schedule_seed.py`

---

## Salesman-all fan-out (Beta)

**What to test:**
- 9am Salesmen Ordered / Shipped seed with `split_by_salesman`.
- Existing plain rows get that flag on re-seed.
- `split_by_salesman` with no key list fans out to active salesmen who have an email.
- Salesman-filtered Ordered omits the By Salesman tab; unscoped Ordered keeps it.
- Monthly combined SharePoint job stays `Salesman Report/Monthly` with no split. A second seed (`Monthly 1st 12am Monthly Salesmen` / `Monthly Salesmen Report`) is split-only, no folder.

**Expected behavior:**
- One combined file (folder/recipients) plus one file per salesman with an email.
- Per-rep Ordered files match live `--salesman all` (no By Salesman sheet).
- Monthly SharePoint job is unchanged. The extra monthly split schedule emails each salesman and does not write SharePoint.

**Test files:** `v3/tests/test_schedule_seed.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_report_ordered.py`, `v3/tests/test_report_service.py`, `v3/tests/test_salesmen_seed.py`

## Salesman-scoped invoiced fetch

**What to test:**
- A one-day salesman-scoped invoiced report requests only its selected date range.
- Beta: salesman filter, `_skip_commissions`, or a layout `order` without `commissions` skips the YTD pull and omits the Commissions tab.
- Unscoped Invoiced still YTD-fetches for commissions.

**Expected behavior:**
- Salesman-scoped / shipped reports do not fetch year-to-date data because their output omits the commissions tab.
- Daily 9am Salesmen Shipped (layout without commissions) fetches only the selected period.

**Edge cases:**
- An unscoped report keeps the existing year-to-date query for its commissions tab.
- Empty/missing layout `order` still fetches YTD (old schedules).

**Test files:** `tests/test_invoiced_loader.py`, `v3/tests/test_report_service.py`, `v3/tests/test_report_invoiced.py`, `v3/tests/test_delivery.py`

---

## v3 master schedule split-email MVP

**What to test:**
- Admins and managers see company schedules on `/schedules`; salesmen see My schedules plus the shared Add wizard, never the company list.
- Managers can create/share; they edit only rows they created or that run as them. Other shared rows are read-only with an admin note.
- Private master rows stay off the company list and show under My schedules for the owner.
- A manager-owned master run is scoped to that manager’s salesman keys. Unscoped (no owner/run-as, or privileged owner) stays unrestricted.
- Master schedule params persist salesman delivery flags (`split_by_salesman`, `email_to_salesmen`, `email_salesman_keys`).
- Master schedule delivery sends the full workbook to typed recipients/SharePoint and split salesman-filtered files to `salesmen.email`.

**Expected behavior:**
- `/master-schedules` redirects managers and admins to `/schedules#company`; salesmen get 403. API create/update stay company-viewer gated; salesmen still 403 on create.
- Salesman split emails use raw SalesGroup values for report params and normalized keys only for email lookup.

**Edge cases:**
- A master schedule with only salesman email targets can be saved.
- Missing salesman email is recorded as a failed requested delivery.

**Test files:** `v3/tests/test_blueprints.py`, `v3/tests/test_scheduling.py`, `v3/tests/test_salesmen_seed.py`.

---

## Cancel a running report job

**What to test:**
- A queued job can be cancelled (it never starts).
- A running job can be cancelled (the user can stop a run stuck on a slow Reporting API call).
- A finished job (success/failure/already-cancelled) cannot be cancelled.
- The cancel endpoint is owner-scoped: one user cannot cancel another user's job.
- Cancelling does not get clobbered: when the slow upstream call finally returns, the late `mark_success`/`mark_failure` is a no-op because it's guarded to `status='running'`.
- The report view renders the Cancel button and its endpoint URL.

**Expected behavior:**
- `JobRepository.cancel` returns True and sets status to `cancelled` for queued OR running jobs; False for terminal jobs.
- `POST /api/jobs/<id>/cancel` returns `{cancelled, status}`; 404 for a job the caller doesn't own.
- On screen: clicking Cancel stops the poll loop within ~1s, shows "Run cancelled.", and the Run button is re-enabled.

**Edge cases:**
- The worker thread for a running job stays blocked until the upstream call ends; cancellation only stops the screen waiting and prevents the result from being shown/stored — it does not force-kill the in-flight HTTP request.

**Test files:** `v3/tests/test_jobs.py` (repo behavior), `v3/tests/test_blueprints.py` (endpoint + template).

---

## Scheduling (rebuild): cadence, Shabbos skip, deliveries, management UI

**What to test:**
- Cadence: a daily/weekly/monthly schedule is "due" only at/after its time, only on its day, and at most once per Eastern day (the `last_run_at` guard). Bad cadence (weekly with no day, unknown frequency) is rejected with a clear message.
- Shabbos/Yom Tov: inside a candle->havdalah window is restricted (Shabbos, or the named Yom Tov); outside is not. The check fails OPEN on any error, including a malformed-but-successful Hebcal response (a calendar hiccup must never block every send).
- Deliveries: a `self` schedule scopes to the owner's allowed salesmen and addresses owner + extras; an unmapped owner produces no delivery; a privileged owner scopes to "all". A `master` schedule produces one send per salesman number, each scoped to ONLY that salesman, addressed to the people mapped to that salesman plus extras; a salesman with no recipients at all is skipped.
- Poller: a due schedule is queued at most once per day (it's stamped as run the moment the durable job is queued, so a timed-out/failed job can't re-fire it that day).
- Catch-up after Shabbos: a run skipped for Shabbos flags `catch_up_pending` (and stamps the day so the cadence doesn't also fire it); once Hebcal says it's no longer restricted, the poller queues the catch-up under a separate dedup key; the run handler clears the flag when it actually runs.
- Failure alerts: a run where every attempted delivery failed (and wasn't cancelled) emails the owner a heads-up and, for a private schedule, creates one in-app notification tied to that schedule. A manual "Run now" queues a job with `manual:true` and ignores the Shabbos skip; running it dismisses the matching notification. A person can't dismiss someone else's notification (403).
- Authorization: only admins reach `/admin/schedules`; a regular owner can manage their own self-schedule but NOT a master schedule and NOT someone else's; every state-changing POST carries CSRF.

**Expected behavior:**
- `cadence.due_now/normalize/describe` behave as above; `sabbath.melacha_assur` returns `(bool, reason)` and never raises.
- `run.expand_deliveries` returns the correct scoped deliveries; `run_schedule` writes a `schedule.run` audit line per delivery (sent/failed/skipped) and stamps the schedule.
- Routes return 200 for allowed pages, 403 for disallowed management, 302 (redirect + flash) for bad input instead of 500.

**Edge cases:**
- A wide master schedule runs its salesmen sequentially inside one worker job capped at `max_job_seconds`; very large ones may need splitting (noted in DECISION-LOG).
- A failed or refused (unconfigured mailer) send is still audited and still consumes the day's run.

**Test files:** `v3/tests/test_scheduling.py` (and related v3 schedule tests). Rebuild's copies of these files were deleted with `rebuild/`.
