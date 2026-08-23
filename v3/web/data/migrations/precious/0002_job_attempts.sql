-- Count how many times crash-recovery has requeued a job. A run that keeps
-- killing its own process (classically an out-of-memory report the OS SIGKILLs,
-- so the worker never gets to mark it failed) would otherwise be requeued on
-- every restart forever - an infinite crash loop that takes the whole site down.
-- recover_orphans() uses this to give up and fail the job after a few tries.
ALTER TABLE jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
