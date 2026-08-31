-- 0019 defaulted every existing schedule_runs row to scheduled, including
-- Send now. This file runs in the same first Production boot as 0019, before
-- any new clock run is written, so every scheduled row here is historical.
-- last_run_at ignores legacy so a deploy-day Send now cannot eat the clock slot.
UPDATE schedule_runs SET trigger = 'legacy' WHERE trigger = 'scheduled';
