-- precious.db initial schema (durable app state). Litestream-replicated in prod.
-- Foreign keys are ON (see connection.py). All timestamps are ISO-8601 text (UTC).

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL DEFAULT '',
    role            TEXT NOT NULL DEFAULT 'salesman',   -- admin|developer|manager|salesman
    is_active       INTEGER NOT NULL DEFAULT 1,
    is_external     INTEGER NOT NULL DEFAULT 0,
    dashboard_enabled INTEGER NOT NULL DEFAULT 0,
    sharepoint_access INTEGER NOT NULL DEFAULT 0,
    test_access     INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS salesmen (
    key             TEXT PRIMARY KEY,                   -- normalized lowercase alnum
    number          TEXT NOT NULL DEFAULT '',
    full_name       TEXT NOT NULL DEFAULT '',
    display_name    TEXT NOT NULL DEFAULT '',
    email           TEXT NOT NULL DEFAULT '',
    commission_pct  REAL NOT NULL DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    is_external     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS user_salesman_access (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    salesman_key    TEXT NOT NULL REFERENCES salesmen(key) ON DELETE CASCADE,
    PRIMARY KEY (user_id, salesman_key)
);

CREATE TABLE IF NOT EXISTS user_report_access (
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    report_key      TEXT NOT NULL,
    allowed         INTEGER NOT NULL DEFAULT 1,          -- explicit allow/deny override
    PRIMARY KEY (user_id, report_key)
);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme           TEXT NOT NULL DEFAULT 'light',
    landing_page    TEXT NOT NULL DEFAULT 'reports',
    default_report_tab TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS user_exclusions (
    user_id          INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    customer_account TEXT NOT NULL,
    PRIMARY KEY (user_id, customer_account)
);

CREATE TABLE IF NOT EXISTS saved_reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    report_key      TEXT NOT NULL,
    name            TEXT NOT NULL,
    params_json     TEXT NOT NULL DEFAULT '{}',
    layout_json     TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (user_id, report_key, name)
);

CREATE TABLE IF NOT EXISTS schedules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    report_key      TEXT NOT NULL,
    params_json     TEXT NOT NULL DEFAULT '{}',
    layout_json     TEXT NOT NULL DEFAULT '{}',
    cadence         TEXT NOT NULL DEFAULT '',
    recipients      TEXT NOT NULL DEFAULT '',
    sharepoint_path TEXT NOT NULL DEFAULT '',
    is_active       INTEGER NOT NULL DEFAULT 1,
    start_date      TEXT,
    end_date        TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS master_schedules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    report_key      TEXT NOT NULL,
    name            TEXT NOT NULL,
    params_json     TEXT NOT NULL DEFAULT '{}',
    layout_json     TEXT NOT NULL DEFAULT '{}',
    cadence         TEXT NOT NULL DEFAULT '',
    recipients      TEXT NOT NULL DEFAULT '',   -- admin-only sensitive field
    sharepoint_path TEXT NOT NULL DEFAULT '',
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schedule_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    -- Intentionally no FK: schedule_id is polymorphic (points at schedules OR
    -- master_schedules per schedule_type). Integrity enforced in the repo layer.
    schedule_id     INTEGER,
    schedule_type   TEXT NOT NULL DEFAULT 'personal',   -- personal|master
    status          TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT,
    rows            INTEGER,
    output_meta     TEXT NOT NULL DEFAULT '{}',
    debug_log       TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS report_run_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id) ON DELETE SET NULL,
    report_key      TEXT NOT NULL,
    params_hash     TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL,
    rows            INTEGER,
    duration_ms     INTEGER,
    source          TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,
    payload_json    TEXT NOT NULL DEFAULT '{}',
    dismissed       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    read_at         TEXT
);

CREATE TABLE IF NOT EXISTS outbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject         TEXT NOT NULL DEFAULT '',
    recipients      TEXT NOT NULL DEFAULT '',
    attachment_meta TEXT NOT NULL DEFAULT '{}',
    sharepoint_meta TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'queued',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS feature_flags (
    key             TEXT PRIMARY KEY,
    enabled         INTEGER NOT NULL DEFAULT 0,
    description     TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS app_settings (
    key             TEXT PRIMARY KEY,
    value           TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS magic_link_tokens (
    token_hash      TEXT PRIMARY KEY,
    email           TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    used            INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Durable job queue (plan section 10 / gpt55 concession): source of truth for
-- job state so jobs survive a B1 restart and dedup works across restarts.
CREATE TABLE IF NOT EXISTS jobs (
    id              TEXT PRIMARY KEY,                    -- uuid / run_id
    type            TEXT NOT NULL,                       -- report.run, report.export, ...
    status          TEXT NOT NULL DEFAULT 'queued',      -- queued|running|success|failure|cancelled
    owner_user_id   INTEGER REFERENCES users(id) ON DELETE SET NULL,
    dedup_key       TEXT,                                -- params+scope hash; NULL = never dedup
    progress        INTEGER NOT NULL DEFAULT 0,
    params_json     TEXT NOT NULL DEFAULT '{}',
    result_ref      TEXT NOT NULL DEFAULT '',            -- pointer into cache.report_payload_cache / file
    error           TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    started_at      TEXT,
    finished_at     TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_dedup_active
    ON jobs(dedup_key) WHERE dedup_key IS NOT NULL AND status IN ('queued', 'running');
