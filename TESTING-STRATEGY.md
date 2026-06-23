# Testing Strategy

Testing plan built alongside code. Each feature/module gets an entry documenting what to test, expected behavior, and edge cases. See `testing-protocol.mdc` for rules.

A cheaper model can use this file as a guide to run the full test suite without deep context.

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

**Test files:** `rebuild/tests/test_scheduling.py` (cadence, sabbath, deliveries), `rebuild/tests/test_schedule_routes.py` (authz, CSRF, once-a-day, catch-up after Shabbos, whole-run failure notify, manual run-now + ignore-Shabbos, notification ownership), `rebuild/tests/test_email.py` (failure-notice composition, escaping, audited-when-off).
