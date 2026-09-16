-- Per-customer dashboard aggregates (cache.db). Rebuildable from the Reporting
-- API; mirrors LIVE's dashboard_cache per-customer shape so the tiles + activity
-- table read precomputed metrics rather than recomputing on every request.
-- The generic mirror_dashboard_cache (key/payload) stays for ad-hoc cached blobs.

CREATE TABLE IF NOT EXISTS dashboard_customers (
    customer_account  TEXT PRIMARY KEY,
    customer_name     TEXT NOT NULL DEFAULT '',
    sales_group       TEXT NOT NULL DEFAULT '',
    last_order_date   TEXT,
    order_count       INTEGER NOT NULL DEFAULT 0,
    avg_gap_days      REAL,
    gap_stdev         REAL,
    overdue_threshold REAL,
    days_since_last   INTEGER,
    status            TEXT NOT NULL DEFAULT 'new',
    refreshed_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dashcust_group ON dashboard_customers(sales_group);
CREATE INDEX IF NOT EXISTS idx_dashcust_status ON dashboard_customers(status);
