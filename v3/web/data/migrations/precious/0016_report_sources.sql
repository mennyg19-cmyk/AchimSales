CREATE TABLE IF NOT EXISTS beta_report_sources (
    report_key TEXT PRIMARY KEY,
    source TEXT NOT NULL CHECK(source IN ('sql', 'odata')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT OR IGNORE INTO beta_report_sources (report_key, source) VALUES
    ('ordered', 'sql'),
    ('invoiced', 'sql'),
    ('salesman', 'sql'),
    ('number_4', 'odata'),
    ('customer_activity', 'sql'),
    ('customer_last_order', 'odata'),
    ('item_averages', 'odata'),
    ('customer_aging', 'odata');
