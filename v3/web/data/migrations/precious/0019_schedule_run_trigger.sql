-- Manual Send now vs the clock. last_run_at ignores manual so a person hitting
-- Send now cannot eat the real scheduled slot later that day.
ALTER TABLE schedule_runs ADD COLUMN trigger TEXT NOT NULL DEFAULT 'scheduled';
