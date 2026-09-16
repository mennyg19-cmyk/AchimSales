-- Save / On should not fire a catch-up. Claimed time is hidden from the run log.
ALTER TABLE schedules ADD COLUMN last_claimed_at TEXT;
ALTER TABLE master_schedules ADD COLUMN last_claimed_at TEXT;
