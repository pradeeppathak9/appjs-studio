-- Fair rotation for the redemption state sync.
--
-- Selecting the backlog by created_at starves: polling oldest-first re-reads the
-- same never-resolving rows every run, so once the backlog outgrew the per-run
-- cap the middle became unreachable. Ordering by when a row was last polled
-- rotates through all of it regardless of size.
--
-- The index is partial on non-terminal rows, which is the only set the sync ever
-- selects, and CONCURRENTLY so it does not lock the table.
--
--   docker compose exec backend python migrations/apply.py migrations/005_txn_poll_queue.sql

ALTER TABLE phonepe_subscription_transactions ADD COLUMN IF NOT EXISTS last_polled_at TIMESTAMPTZ;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_txn_poll_queue
  ON phonepe_subscription_transactions (last_polled_at ASC NULLS FIRST)
  WHERE state NOT IN ('FAILED', 'COMPLETED', 'REVOKED', 'CANCELLED');
