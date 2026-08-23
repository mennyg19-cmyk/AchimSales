-- Daily 9am was a Live Azure job. Beta boot kept re-inserting it after delete.
DELETE FROM master_schedules WHERE is_shared = 1 AND name = 'Daily 9am';
