-- Frozen report window and remote filename. Do not edit 0023 or 0024.
-- Retry must send the original attempt, not skip or PUT a new {HH}{mm} name.
ALTER TABLE delivery_legs ADD COLUMN window_from TEXT NOT NULL DEFAULT '';
ALTER TABLE delivery_legs ADD COLUMN window_to TEXT NOT NULL DEFAULT '';
ALTER TABLE delivery_legs ADD COLUMN filename TEXT NOT NULL DEFAULT '';
