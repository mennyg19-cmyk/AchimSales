-- Silent dual-path workbook parity while JSON and normalized views coexist.
-- New layout is delivered; old JSON layout is built to disk and scored here.
-- A daily digest email summarizes matches / diffs.

CREATE TABLE IF NOT EXISTS view_workbook_parity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    report_key TEXT NOT NULL,
    view_name TEXT NOT NULL DEFAULT '',
    view_id TEXT,
    schedule_kind TEXT NOT NULL DEFAULT '',
    schedule_id INTEGER,
    schedule_name TEXT NOT NULL DEFAULT '',
    matched INTEGER NOT NULL,
    row_count INTEGER NOT NULL DEFAULT 0,
    old_path TEXT NOT NULL DEFAULT '',
    new_path TEXT NOT NULL DEFAULT '',
    diff_summary TEXT NOT NULL DEFAULT '',
    digest_date TEXT
);

CREATE INDEX IF NOT EXISTS idx_view_workbook_parity_created
    ON view_workbook_parity(created_at);
CREATE INDEX IF NOT EXISTS idx_view_workbook_parity_digest
    ON view_workbook_parity(digest_date);
