-- When a scheduled send is skipped because it's Shabbos/Yom Tov, we flag it here
-- so the poller can fire it as a catch-up the moment the day is over, instead of
-- silently waiting until the cadence comes around again.
ALTER TABLE schedules ADD COLUMN catch_up_pending INTEGER NOT NULL DEFAULT 0;
