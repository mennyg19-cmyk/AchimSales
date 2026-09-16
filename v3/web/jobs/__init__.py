"""In-process background work for a single B1 instance (plan section 10).

- JobWorker: a BOUNDED thread pool that drains the durable `jobs` table. The DB
  is the source of truth, so jobs survive restarts and dedup works across them.
- Scheduler: an APScheduler wrapper for periodic work (mirror refresh, scheduled
  report emails, distributions). Single instance => exactly one owner, so the old
  "scheduler owner election" + fail-open locks are unnecessary.

No Redis, no separate worker dyno on B1; a separate worker App Service is the
documented first scale step.
"""
