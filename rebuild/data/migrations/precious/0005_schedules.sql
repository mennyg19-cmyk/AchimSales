-- A saved, repeating report send. The poller checks these every minute and, when
-- one is due (its cadence says so and it hasn't already fired today), drops a
-- schedule.run job that builds the report scoped to each recipient and emails it.
--
-- kind:
--   'self'   -- a person scheduling a report for themselves (and any extra
--              recipients they list); the data is scoped to that owner.
--   'master' -- an admin schedule that splits one report by salesman number:
--              each number in `salesmen` gets its own scoped run, emailed to the
--              people mapped to that salesman (plus any extra recipients).
--
-- filters/cadence/recipients/salesmen are JSON text (the app owns their shape).
-- last_run_at is the once-per-day guard: the cadence won't re-fire on a day it
-- already ran (compared in US/Eastern, the business timezone).

CREATE TABLE schedules (
  id TEXT PRIMARY KEY,
  owner_email TEXT NOT NULL,
  report_key TEXT NOT NULL,
  title TEXT NOT NULL,
  kind TEXT NOT NULL,
  filters TEXT NOT NULL DEFAULT '{}',
  cadence TEXT NOT NULL,
  recipients TEXT NOT NULL DEFAULT '[]',
  salesmen TEXT NOT NULL DEFAULT '[]',
  tab_key TEXT,
  skip_sabbath INTEGER NOT NULL DEFAULT 1,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_run_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX idx_schedules_due ON schedules (enabled, kind);

CREATE INDEX idx_schedules_owner ON schedules (owner_email);
