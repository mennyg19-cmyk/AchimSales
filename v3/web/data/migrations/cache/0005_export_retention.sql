-- Tiered export retention: one-time (7d), scheduled (30d), master (forever).
-- Also tracks owner for history browsing and snapshot auto-save.
ALTER TABLE report_exports ADD COLUMN export_type TEXT NOT NULL DEFAULT 'one_time';
ALTER TABLE report_exports ADD COLUMN owner_email TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_exports_type ON report_exports(export_type);
CREATE INDEX IF NOT EXISTS idx_exports_owner ON report_exports(owner_email);
CREATE INDEX IF NOT EXISTS idx_exports_built ON report_exports(built_at);
