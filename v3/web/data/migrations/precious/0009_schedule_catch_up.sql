-- Owed send after a Shabbos/Yom Tov skip (clock catch-up after havdalah).
ALTER TABLE schedules ADD COLUMN catch_up_pending INTEGER NOT NULL DEFAULT 0;
ALTER TABLE master_schedules ADD COLUMN catch_up_pending INTEGER NOT NULL DEFAULT 0;
