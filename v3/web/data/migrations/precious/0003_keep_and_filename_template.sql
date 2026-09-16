-- Keep flag for finished report runs (resume past the default 48h window).
ALTER TABLE jobs ADD COLUMN kept_until TEXT;

-- Optional filename pattern for scheduled deliveries (token language).
ALTER TABLE schedules ADD COLUMN filename_template TEXT NOT NULL DEFAULT '';
ALTER TABLE master_schedules ADD COLUMN filename_template TEXT NOT NULL DEFAULT '';
