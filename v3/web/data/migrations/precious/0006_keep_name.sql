-- Optional display name for a Kept report run (shown on Previously run).
ALTER TABLE jobs ADD COLUMN keep_name TEXT NOT NULL DEFAULT '';
