-- Live per-step log for a running job (Reporting API, workbook, SharePoint, email).
-- The UI polls this so a hang after SQL returns is visible instead of "0%".
ALTER TABLE jobs ADD COLUMN log_json TEXT NOT NULL DEFAULT '[]';
