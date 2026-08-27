-- 0001 created an unused token_hash/used table. Nothing wrote to it.
DROP TABLE IF EXISTS magic_link_tokens;
CREATE TABLE magic_link_tokens (
    token TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    request_ip TEXT
);
CREATE TABLE IF NOT EXISTS magic_link_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    ip TEXT NOT NULL,
    created_at TEXT NOT NULL
);
