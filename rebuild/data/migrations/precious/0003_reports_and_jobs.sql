-- The durable spine for running reports: the job queue, the config that defines
-- each report (columns, tabs, filters), and the incident-proof run log.
-- Every timestamp is ISO-8601 UTC text written by Python (never datetime('now'))
-- and JSON is stored as TEXT, both so a later move to Postgres is a clean swap.

-- One row per report run (or other background task). The worker claims rows
-- here and updates them; the web side only inserts and reads.
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  job_type TEXT NOT NULL,
  report_key TEXT,
  cache_key TEXT,
  params TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'queued',
  attempts INTEGER NOT NULL DEFAULT 0,
  requested_by TEXT,
  scope_token TEXT,
  result_ref TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  claimed_at TEXT,
  heartbeat_at TEXT,
  finished_at TEXT
);

-- At most one active (queued or running) job per cache key, so two clicks on
-- the same report reuse one job instead of piling up duplicates.
CREATE UNIQUE INDEX ux_jobs_active_cache_key
  ON jobs (cache_key)
  WHERE cache_key IS NOT NULL AND status IN ('queued', 'running');

CREATE INDEX ix_jobs_status_created ON jobs (status, created_at);

-- One row per report. status gates whether it can be run (active) or is parked
-- (disabled/backlog). sp_name is the stored procedure that returns its flat table.
CREATE TABLE report_configs (
  report_key TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  sp_name TEXT,
  default_params TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

-- The user-facing filters a report offers (date range, customer, etc.). kind
-- drives the input widget; options is JSON for pick-lists.
CREATE TABLE report_filters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_key TEXT NOT NULL REFERENCES report_configs(report_key) ON DELETE CASCADE,
  filter_key TEXT NOT NULL,
  label TEXT NOT NULL,
  kind TEXT NOT NULL,
  default_value TEXT,
  options TEXT NOT NULL DEFAULT '[]',
  sort_order INTEGER NOT NULL DEFAULT 0,
  UNIQUE (report_key, filter_key)
);

-- The canonical column set for a report, matching the LIVE export format.
-- column_key is the name as it comes out of the flat table (after the adapter).
CREATE TABLE report_columns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_key TEXT NOT NULL REFERENCES report_configs(report_key) ON DELETE CASCADE,
  column_key TEXT NOT NULL,
  label TEXT NOT NULL,
  data_type TEXT NOT NULL DEFAULT 'text',
  format TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0,
  default_hidden INTEGER NOT NULL DEFAULT 0,
  UNIQUE (report_key, column_key)
);

-- The tabs a report shows. Each tab is a recipe over the one flat table:
-- filter -> group -> aggregate -> pick columns -> sort. transform/layout/condition
-- handle the special tabs (commission cards, conditional tabs).
CREATE TABLE report_tabs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_key TEXT NOT NULL REFERENCES report_configs(report_key) ON DELETE CASCADE,
  tab_key TEXT NOT NULL,
  label TEXT NOT NULL,
  sort_order INTEGER NOT NULL DEFAULT 0,
  filter_expr TEXT,
  group_by TEXT NOT NULL DEFAULT '[]',
  aggregations TEXT NOT NULL DEFAULT '{}',
  column_keys TEXT NOT NULL DEFAULT '[]',
  sorters TEXT NOT NULL DEFAULT '[]',
  transform TEXT,
  layout TEXT,
  condition TEXT,
  UNIQUE (report_key, tab_key)
);

-- Incident-proof record of what actually happened: every run/export/delivery.
-- Written by the job handlers, because the job is the source of truth.
CREATE TABLE audit_run_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  user_email TEXT,
  report_key TEXT,
  job_id TEXT,
  action TEXT NOT NULL,
  duration_ms INTEGER,
  status TEXT,
  message TEXT
);

CREATE INDEX ix_audit_ts ON audit_run_log (ts);
