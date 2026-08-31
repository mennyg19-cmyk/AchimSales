-- Frozen enqueue instant on the leg. Do not edit 0023.
-- Retry after the job row is gone still expands {HH}{mm} from this value.
ALTER TABLE delivery_legs ADD COLUMN slot_when TEXT NOT NULL DEFAULT '';
