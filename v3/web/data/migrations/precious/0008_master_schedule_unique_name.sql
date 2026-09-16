-- Company schedule names must be unique so two gunicorn workers cannot
-- double-insert the Azure import on boot.
DELETE FROM master_schedules
 WHERE is_shared = 1
   AND id NOT IN (
     SELECT MIN(id) FROM master_schedules WHERE is_shared = 1 GROUP BY name
   );
CREATE UNIQUE INDEX IF NOT EXISTS master_schedules_shared_name
  ON master_schedules(name) WHERE is_shared = 1;
