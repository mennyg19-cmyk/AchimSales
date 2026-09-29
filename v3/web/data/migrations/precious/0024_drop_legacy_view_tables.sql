-- View format lives on views + layout_* only.
-- This runs after project_from_legacy has copied these rows (see migrate.py).
-- schedules / master_schedules stay; the clock still uses them.

DROP TABLE IF EXISTS saved_reports;
DROP TABLE IF EXISTS company_views;
DROP TABLE IF EXISTS report_defaults;
