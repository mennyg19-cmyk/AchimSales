-- Company schedules: who owns it, whether it is on the shared list, and whose
-- book it runs as (null = unscoped, admin-only). Existing rows stay shared.
ALTER TABLE master_schedules ADD COLUMN owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE master_schedules ADD COLUMN is_shared INTEGER NOT NULL DEFAULT 1;
ALTER TABLE master_schedules ADD COLUMN run_as_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
