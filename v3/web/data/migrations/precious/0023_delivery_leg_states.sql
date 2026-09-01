-- Honest delivery states. Do not edit 0020.
-- leftover pending rows were treated as settled (do not retry) even when the
-- send never happened. unknown is the honest leftover: operator confirms.
ALTER TABLE delivery_legs ADD COLUMN slot_id TEXT NOT NULL DEFAULT '';
ALTER TABLE delivery_legs ADD COLUMN job_id TEXT NOT NULL DEFAULT '';
ALTER TABLE delivery_legs ADD COLUMN upload_session_url TEXT NOT NULL DEFAULT '';

UPDATE delivery_legs SET status='unknown',
  error=CASE WHEN IFNULL(error,'')='' THEN
    'Migrated from pending; confirm whether the mail or file arrived.'
  ELSE error END
WHERE status='pending';

CREATE INDEX IF NOT EXISTS idx_delivery_legs_job ON delivery_legs(job_id);
CREATE INDEX IF NOT EXISTS idx_delivery_legs_slot ON delivery_legs(slot_id);
CREATE INDEX IF NOT EXISTS idx_delivery_legs_updated ON delivery_legs(updated_at);

-- No FK to jobs or schedule_runs: those rows prune on a different clock.
-- Legs are kept for 90 days (Q10) via DeliveryLegRepository.prune.
