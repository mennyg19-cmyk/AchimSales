-- Global per-report on/off (Live report_config). Missing row = enabled.
CREATE TABLE IF NOT EXISTS report_config (
    report_key TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1
);
