-- Distinguish explicit group:[] (ungroup) from a missing group key (builder default).

ALTER TABLE layout_tabs ADD COLUMN groups_explicit INTEGER NOT NULL DEFAULT 1
    CHECK (groups_explicit IN (0, 1));
