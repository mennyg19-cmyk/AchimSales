-- Company-wide Default view per report, plus a name on each schedule so the
-- list can show Default vs a saved view. Existing schedules never picked a
-- named view, so they stay Default.
CREATE TABLE IF NOT EXISTS report_defaults (
    report_key TEXT PRIMARY KEY,
    params_json TEXT NOT NULL DEFAULT '{}',
    layout_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL
);

ALTER TABLE schedules ADD COLUMN view_name TEXT NOT NULL DEFAULT 'Default';
ALTER TABLE master_schedules ADD COLUMN view_name TEXT NOT NULL DEFAULT 'Default';
