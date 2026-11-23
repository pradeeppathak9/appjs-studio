-- 002_pending_activation_created_at.sql
--
--   docker compose exec backend python migrations/apply.py \
--       migrations/002_pending_activation_created_at.sql
--
-- 001 indexed the pending-activation set on (app_id) alone, which was right when
-- that set was ~3.6k rows. A client retry storm on 2026-09-10 grew it to 102,862
-- rows, and _sync_subscription_state is now bounded to recent rows only
-- (SYNC_STATE_MAX_AGE_HOURS / SYNC_STATE_MAX_ROWS_PER_RUN in
-- workers/phone_worker_helper.py) rather than polling PhonePe once per row.
--
-- Adding created_at lets that bounded query seek straight to the newest rows and
-- stop, instead of scanning the whole partial index and sorting.

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_subs_pending_activation_created
    ON phonepe_subscriptions (app_id, created_at DESC)
    WHERE state IN ('INITIATED', 'ACTIVATION_IN_PROGRESS');

DROP INDEX CONCURRENTLY IF EXISTS ix_phonepe_subs_pending_activation;

ANALYZE phonepe_subscriptions;
