-- cache.db initial schema (disposable D365 mirror + report payload cache).
-- NOT replicated; fully rebuildable from the Reporting API. Clearly labeled cache.

CREATE TABLE IF NOT EXISTS mirror_customers (
    customer_account TEXT PRIMARY KEY,
    customer_name    TEXT NOT NULL DEFAULT '',
    sales_group      TEXT NOT NULL DEFAULT '',
    raw_json         TEXT NOT NULL DEFAULT '{}',
    refreshed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mirror_salesline (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number     TEXT NOT NULL DEFAULT '',
    line_num         TEXT NOT NULL DEFAULT '',
    customer_account TEXT NOT NULL DEFAULT '',
    sales_group      TEXT NOT NULL DEFAULT '',
    order_date       TEXT NOT NULL DEFAULT '',
    raw_json         TEXT NOT NULL DEFAULT '{}',
    refreshed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_salesline_order ON mirror_salesline(order_number);
CREATE INDEX IF NOT EXISTS idx_salesline_cust ON mirror_salesline(customer_account);

CREATE TABLE IF NOT EXISTS mirror_sales_header (
    order_number     TEXT PRIMARY KEY,
    customer_account TEXT NOT NULL DEFAULT '',
    sales_group      TEXT NOT NULL DEFAULT '',
    order_date       TEXT NOT NULL DEFAULT '',
    raw_json         TEXT NOT NULL DEFAULT '{}',
    refreshed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mirror_invoice (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number   TEXT NOT NULL DEFAULT '',
    customer_account TEXT NOT NULL DEFAULT '',
    sales_group      TEXT NOT NULL DEFAULT '',
    invoice_date     TEXT NOT NULL DEFAULT '',
    raw_json         TEXT NOT NULL DEFAULT '{}',
    refreshed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_invoice_num ON mirror_invoice(invoice_number);

CREATE TABLE IF NOT EXISTS mirror_invoice_lines (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number   TEXT NOT NULL DEFAULT '',
    item_number      TEXT NOT NULL DEFAULT '',
    raw_json         TEXT NOT NULL DEFAULT '{}',
    refreshed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_invline_num ON mirror_invoice_lines(invoice_number);

CREATE TABLE IF NOT EXISTS mirror_dashboard_cache (
    cache_key        TEXT PRIMARY KEY,
    payload_json     TEXT NOT NULL DEFAULT '{}',
    built_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mirror_refresh_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    kind             TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT '',
    started_at       TEXT,
    finished_at      TEXT,
    rows             INTEGER,
    detail           TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS mirror_backfill_jobs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    range_start      TEXT NOT NULL DEFAULT '',
    range_end        TEXT NOT NULL DEFAULT '',
    status           TEXT NOT NULL DEFAULT 'queued',
    progress         INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ONE report cache (plan section 7). Key includes scope + builder version + freshness
-- so cached payloads never leak across users/scopes (enforced + tested later).
CREATE TABLE IF NOT EXISTS report_payload_cache (
    cache_key        TEXT PRIMARY KEY,   -- hash(report_key, params, user_scope, builder_version, freshness)
    report_key       TEXT NOT NULL,
    payload_json     TEXT NOT NULL,
    built_at         TEXT NOT NULL DEFAULT (datetime('now'))
);
