-- Store magic-link tokens as hashes. Plaintext rows from 0017 are 15-minute
-- one-shots; dropping them is safer than migrating secrets we should not have kept.
DROP TABLE IF EXISTS magic_link_tokens;
CREATE TABLE magic_link_tokens (
    token_hash TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    consumed_at TEXT,
    request_ip TEXT
);
