CREATE TABLE IF NOT EXISTS external_recipients (
    email TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    requested_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    decided_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    decided_at TEXT
);
