CREATE TABLE IF NOT EXISTS delivery_legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT,
    run_id INTEGER,
    slot_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('email', 'folder', 'notice')),
    status TEXT NOT NULL CHECK (status IN ('prepared', 'sending', 'accepted', 'sent', 'failed', 'unknown')),
    error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_delivery_legs_job_id ON delivery_legs(job_id);
CREATE INDEX IF NOT EXISTS idx_delivery_legs_slot_id ON delivery_legs(slot_id);
