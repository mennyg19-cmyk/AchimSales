-- One row per email or SharePoint/OneDrive leg. Retry skips sent/pending
-- (pending = Graph accepted or we were about to send; do not double-send).
CREATE TABLE IF NOT EXISTS delivery_legs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        INTEGER,
    attempt_key   TEXT NOT NULL UNIQUE,
    kind          TEXT NOT NULL,
    target        TEXT NOT NULL DEFAULT '',
    salesman_key  TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL,
    error         TEXT NOT NULL DEFAULT '',
    row_count     INTEGER NOT NULL DEFAULT 0,
    remote_id     TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_delivery_legs_run ON delivery_legs(run_id);
