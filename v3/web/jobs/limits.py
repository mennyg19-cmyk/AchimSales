"""B1 job-worker bounds. Env overrides are for tests, not a second config surface."""

from __future__ import annotations

import os

JOB_TIMEOUT_SECONDS = int(os.environ.get("JOB_TIMEOUT_SECONDS", str(45 * 60)))
WORKER_BEAT_EVERY_SECONDS = 15
WORKER_HEARTBEAT_STALE_SECONDS = 90
SCHEDULER_HEARTBEAT_STALE_SECONDS = 180
MAX_QUEUED_JOBS = 40
MAX_QUEUE_AGE_SECONDS = 20 * 60

# claim_next sorts by this first (lower = sooner), then created_at.
PRIORITY_SQL = (
    "CASE type WHEN 'schedule.run' THEN 0 "
    "WHEN 'report.deliver' THEN 1 ELSE 2 END"
)
ADMISSION_EXEMPT_TYPES = frozenset({"schedule.run", "lookups.refresh", "dashboard.refresh"})

# Crash recovery requeues cache/export/mirror work. These send mail; a restart
# must not run them again. recover_orphans cancels them instead.
UNSAFE_RECOVERY_TYPES = frozenset({"schedule.run", "report.deliver"})
