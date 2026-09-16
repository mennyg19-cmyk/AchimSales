-- Named company-wide views (shared layouts everyone can pick on schedules).
CREATE TABLE IF NOT EXISTS company_views (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_key TEXT NOT NULL,
    name TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    layout_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE (report_key, name)
);
