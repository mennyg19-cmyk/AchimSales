-- Immutable copy of a Kept report payload. cache.db is disposable; this table
-- is on precious.db so Keep this run survives recycle and cache prune.
CREATE TABLE IF NOT EXISTS kept_run_payloads (
    job_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    copied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
