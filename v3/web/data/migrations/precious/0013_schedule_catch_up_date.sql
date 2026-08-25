-- Skipped slot's Eastern date so a Shabbos makeup can cover that day's window.
ALTER TABLE schedules ADD COLUMN catch_up_for_date TEXT;
ALTER TABLE master_schedules ADD COLUMN catch_up_for_date TEXT;
