Model: grok-4.3

Proof-of-read: codegraph_explore on "Area C platform..." returned 157 symbols/40 files + verbatim source for config.py, __init__.py, msal_flow.py, principal.py, authorization.py, session.py, connection.py, worker.py, blueprints/auth.py (plus scheduler/runner excerpts). All reads via codegraph_node (no tree grep). Cross-checked against REBUILD-BRIEF.md and C-platform.md backbones. Covered every required area for invoiced + shell.

C1. Entra / Microsoft login flow
C1.1 msal_flow.py: build_login_url initiates auth-code flow (scopes from cfg, redirect_uri forces https behind proxy), stores flow in session; complete_login acquires token, extracts email/name from id_token_claims (preferred_username/email/upn), errors on missing flow or no email claim. Used by blueprints/auth.py login_page (msal mode) + callback.
C1.2 blueprints/auth.py: /login redirects to MSAL or shows dev form (only if AUTH_MODE=dev else 403); /auth/callback calls complete_login then UserRepository.upsert + login; /logout clears session; impersonate_* (developer-only, checks is_privileged live).
C1.3 session.py: current_principal / login / logout use _SESSION_KEY="v3_user" + Principal.from/to_dict; sync_role updates cached role without touching identity (presentation only; authz always re-resolves from DB).

C2. Principal / roles model + central authorization
C2.1 principal.py: Principal dataclass (email, name, role, is_dev, impersonating, real_*); roles ROLE_ADMIN/DEVELOPER/MANAGER/SALESMAN; _PRIVILEGED={admin,developer}; is_privileged property.
C2.2 authorization.py: Authorization (single source, injected everywhere): _active_user re-fetches from UserRepository (fail-closed on inactive/unknown); visible_salesman_keys returns set or None=unrestricted (privileged only); can_view_report checks registry + explicit user_report_access row or _role_default (manager all, salesman only salesman_default); assert_* raise Forbidden(403); authorize_delivery re-resolves live scope + SharePoint check for deferred runs; has_sharepoint_access from user flag (privileged bypass).

C3. Admin user + report/salesman-access management
C3.1 blueprints/admin.py (inferred from callers + authz): user list, role grants, user_report_access (allowed/deny/inherit), user_salesman_access rows; impersonation UI.
C3.2 __init__.py _seed_* : V3_ADMIN_EMAILS / V3_DEVELOPER_EMAILS upsert to users (role, active); seed_users_from_live mirrors live directory; _seed_salesmen_if_empty from xlsx.

C4. Settings / theme / preferences
C4.1 __init__.py context: loads theme from user_preferences on precious; dashboard_enabled / test_site_enabled / order_entry_enabled from feature_flags + per-user flags (privileged bypass).
C4.2 blueprints/settings.py: theme/preferences persistence (not detailed, but referenced).

C5. Durable job worker (enqueue/claim/drain/cancel/recovery/leader)
C5.1 jobs/worker.py: JobWorker (max_workers=2 B1-bound): register(type, handler); claim_next via JobRepository; _run with JobContext.set_progress; recover_orphans on start; BoundedSemaphore + ThreadPoolExecutor; poller loop with heartbeat; drain/process_next for tests.
C5.2 __init__.py: bootstrap_background calls migrate/seed then if _is_background_leader (fcntl flock on .v3-background.lock next to precious.db) starts worker + scheduler; else follower skips.
C5.3 jobs/scheduler.py: APScheduler wrapper (coalesce, misfire_grace 5m, max_instances=1); add_cron queues until start.

C6. Email delivery (recipients, outbox, attachments) + schedule/recurring flow
C6.1 delivery/email.py, service.py, jobs.py: EmailService, DeliveryService.run_and_deliver (builds via runner, sends SMTP or writes .eml to outbox, optional SharePoint); delivery job handler.
C6.2 scheduling/runner.py + tick.py + jobs.py: ScheduleRunner.run (load sched, re-authz owner live via principal_for_user_id + authorize_delivery, DeliveryService, record schedule_runs); make_tick enqueues due; master vs personal (MASTER unrestricted).
C6.3 data/repositories/schedules.py: Schedule / MasterSchedule / ScheduleRun rows (params/layout/cadence json, recipients, sharepoint_path).

C7. Audit / run log
C7.1 data/repositories/run_log.py (ReportRunLogRepository): written by report/export/delivery/schedule handlers; incident-proof (app vs endpoint).
C7.2 __init__.py: RUN_LOG_REPO wired; used in report jobs.

C8. DB connection (precious vs cache SQLite) + migrations + repositories
C8.1 data/connection.py: Database (precious_path, cache_path); precious()/cache() context managers (WAL + FK + busy_timeout + retry journal_mode); from_config; _scoped commit/rollback/close.
C8.2 data/migrate.py: schema migrations (flask migrate CLI).
C8.3 repositories/: jobs, users, saved_reports, salesmen, exports, run_log, preferences, notifications, exclusions, feature_flags, schedules (master/personal), outbox (deferred dashboard/schedules noted).

C9. Config / boot-safety (refuse insecure prod, CSRF)
C9.1 config.py: Config dataclass (all env-driven, no secrets hardcoded); is_prod, authority; validate() fail-closed: APP_ENV dev/prod, AUTH_MODE dev/msal, prod forbids dev auth + weak/default secret + missing MSAL/ReportingAPI/LITESTREAM_BLOB_URL, rejects UNC or /home paths for DBs (_is_unc/_is_app_service_home); load_config defaults APP_ENV=prod so unconfigured refuses boot.
C9.2 __init__.py: create_app calls load_config (raises), sets v3_session cookie (SameSite=Lax, secure in prod), init_csrf, wires AUTHZ; bootstrap_background only after.

C10. Deploy / persistence (Azure App Service, Litestream)
C10.1 deploy.ps1 (per backbone): Azure App Service achim-sales-reports, v3 at /test via wsgi.py DispatcherMiddleware.
C10.2 Persistence: local-disk SQLite precious.db (Litestream -> achimsalesreportsv3 / litestream / AchimReportsApp); cache.db disposable; NEVER SMB/Azure Files (WAL coordination fails, worker starves); Postgres documented off-ramp.

Deferred (not inventoried): dashboard repos/metrics/mirror, master schedules details.

Uncertainties: exact column list in user_report_access / schedule_runs / outbox tables (need migrate.py or seed); SharePointService mock vs real when sp_* empty.
