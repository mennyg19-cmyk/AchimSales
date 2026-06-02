-- Background-built Excel exports, stored as blobs keyed by the export job id.
-- Lives in cache.db (not precious.db): exports are large, regenerable, and
-- short-lived, so we keep them OUT of the Litestream-replicated precious file.
-- A reaper prunes old rows; a lost blob just means "re-run the export".
CREATE TABLE IF NOT EXISTS report_exports (
    job_id      TEXT PRIMARY KEY,   -- the report.export job id (also its result_ref)
    report_key  TEXT NOT NULL,
    filename    TEXT NOT NULL,      -- download name, e.g. "ordered.xlsx"
    content     BLOB NOT NULL,      -- the .xlsx bytes
    size_bytes  INTEGER NOT NULL,
    built_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
