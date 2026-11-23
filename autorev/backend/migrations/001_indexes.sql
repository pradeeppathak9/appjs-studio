-- 001_indexes.sql — index tuning for the PhonePe-dominated workload.
--
-- Run against the live database with psql, which autocommits each statement:
--   psql "$AUTOREV_DATABASE_URL" -f backend/migrations/001_indexes.sql
--
-- Every CREATE/DROP here is CONCURRENTLY, so none of them take a write lock on
-- phonepe_subscriptions (~60k rows, ~50k inserts/day). CONCURRENTLY cannot run
-- inside a transaction block — do not wrap this file in BEGIN/COMMIT.
--
-- Baseline that motivated each index (measured 2026-09-04 on the production DB):
--   phonepe_subscriptions      59,726 rows — 86% FAILED, 99.8% one app_id
--                              969 seq scans had read 46.5M tuples
--   ix_phonepe_subscriptions_app_id  21 scans (app_id has 2 distinct values)
--
-- The matching Index() declarations live in app/models/, so a fresh
-- create_all() produces the same schema this script produces.


-- ── phonepe_subscriptions ─────────────────────────────────────────────────────

-- dashboard list_subscriptions: WHERE app_id = ? ORDER BY created_at DESC LIMIT 50
-- and the start_date/end_date range filters. Was: parallel seq scan over 59k rows
-- + top-N heapsort, 1,822 buffers, 30ms per dashboard page load.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_subs_app_created
    ON phonepe_subscriptions (app_id, created_at DESC);

-- public API: /{phone_number}/subscriptions and /{phone_number}/status both filter
-- app_id AND phone_number. The standalone phone_number index made the planner
-- recheck app_id on every heap row.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_subs_app_phone
    ON phonepe_subscriptions (app_id, phone_number);

-- worker _sync_subscription_state: 3,613 of 59,726 rows. The full state index
-- touched 1,660 buffers; the partial index is a fraction of that.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_subs_pending_activation
    ON phonepe_subscriptions (app_id)
    WHERE state IN ('INITIATED', 'ACTIVATION_IN_PROGRESS');

-- workers _advance_payment_dates and _ensure_scheduled_transactions: ACTIVE subs,
-- the latter also requiring next_payment_date IS NOT NULL.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_subs_active_next_payment
    ON phonepe_subscriptions (app_id, next_payment_date)
    WHERE state = 'ACTIVE';

-- worker _archive_failed_subscriptions. Was a full seq scan (cost 2988, 1784
-- buffers, 59,889 rows discarded) every 6 hours, and it is the query whose input
-- grows fastest — 51,909 FAILED rows were created on 2026-09-04 alone.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_subs_failed_created
    ON phonepe_subscriptions (created_at)
    WHERE state = 'FAILED';

-- Superseded by ix_phonepe_subs_app_created (app_id alone has 2 distinct values,
-- so this index could never do useful selection) and ix_phonepe_subs_app_phone.
DROP INDEX CONCURRENTLY IF EXISTS ix_phonepe_subscriptions_app_id;
DROP INDEX CONCURRENTLY IF EXISTS ix_phonepe_subscriptions_phone_number;

-- ix_phonepe_subscriptions_state is deliberately kept: the /summary trial-revenue
-- aggregate filters state IN ('ACTIVE','PAUSED','REVOKED'), which no partial
-- index above covers.


-- ── phonepe_scheduled_transactions ────────────────────────────────────────────

-- worker _notify_redemption_for_due_subscriptions:
--   WHERE state = 'SCHEDULED' AND payment_date <= ?
-- Was a seq scan discarding all 3,967 rows on every hourly run.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_sched_state_payment_date
    ON phonepe_scheduled_transactions (state, payment_date);

-- _ensure_scheduled_transactions' existence check (subscription_id + payment_date)
-- and _subscription_validity_end_date (subscription_id + state, ORDER BY
-- payment_date DESC). Strict superset of the standalone subscription_id index.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_sched_sub_payment_date
    ON phonepe_scheduled_transactions (subscription_id, payment_date DESC);

DROP INDEX CONCURRENTLY IF EXISTS ix_phonepe_scheduled_transactions_state;
DROP INDEX CONCURRENTLY IF EXISTS ix_phonepe_scheduled_transactions_subscription_id;


-- ── phonepe_subscription_transactions ─────────────────────────────────────────

-- The "latest attempt for this scheduled transaction" lookup, run once per
-- IN_PROGRESS row by _sync_scheduled_transactions and once per page by the
-- dashboard's /scheduled endpoint. The DESC ordering lets the sort disappear.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_txn_sched_created
    ON phonepe_subscription_transactions (scheduled_transaction_id, created_at DESC);

-- list_subscription_transactions: WHERE subscription_id = ? ORDER BY created_at DESC
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_txn_sub_created
    ON phonepe_subscription_transactions (subscription_id, created_at DESC);

DROP INDEX CONCURRENTLY IF EXISTS ix_phonepe_subscription_transactions_scheduled_transaction_id;
DROP INDEX CONCURRENTLY IF EXISTS ix_phonepe_subscription_transactions_subscription_id;

-- ix_phonepe_subscription_transactions_state is kept for the /summary revenue
-- aggregate (state = 'COMPLETED').


-- ── phonepe_subscriptions_archive ─────────────────────────────────────────────
-- Write-mostly and about to grow by ~50k rows/day, so it carries the minimum:
-- one composite for support lookups, one for archived_at retention pruning.
-- All three existing indexes had 0 scans.

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_subs_archive_app_phone
    ON phonepe_subscriptions_archive (app_id, phone_number);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_phonepe_subs_archive_archived_at
    ON phonepe_subscriptions_archive (archived_at);

DROP INDEX CONCURRENTLY IF EXISTS ix_phonepe_subscriptions_archive_state;
DROP INDEX CONCURRENTLY IF EXISTS ix_phonepe_subscriptions_archive_app_id;
DROP INDEX CONCURRENTLY IF EXISTS ix_phonepe_subscriptions_archive_phone_number;


-- ── razorpay ──────────────────────────────────────────────────────────────────
-- Effectively empty today, but the webhook handler's lookups are unindexed and
-- would seq-scan from the first live merchant onward.

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_razorpay_subs_app_created
    ON razorpay_subscriptions (app_id, created_at DESC);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_razorpay_subs_app_phone
    ON razorpay_subscriptions (app_id, phone_number);
-- webhook payment.authorized / order.paid
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_razorpay_subs_app_order
    ON razorpay_subscriptions (app_id, razorpay_order_id);
-- webhook payment.captured / payment.failed
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_razorpay_txn_order
    ON razorpay_transactions (razorpay_order_id);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_razorpay_txn_sub_created
    ON razorpay_transactions (subscription_id, created_at DESC);

DROP INDEX CONCURRENTLY IF EXISTS ix_razorpay_subscriptions_app_id;
DROP INDEX CONCURRENTLY IF EXISTS ix_razorpay_subscriptions_phone_number;
DROP INDEX CONCURRENTLY IF EXISTS ix_razorpay_transactions_subscription_id;


-- ── app_users ─────────────────────────────────────────────────────────────────
-- The PK is (user_id, app_id), so filters on app_id alone — every admin
-- "who owns this app" query, plus the ON DELETE CASCADE from apps — had no index.
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_app_users_app_id
    ON app_users (app_id);


-- ── users ─────────────────────────────────────────────────────────────────────
-- ix_users_id duplicates users_pkey exactly.
DROP INDEX CONCURRENTLY IF EXISTS ix_users_id;


-- ── autovacuum ────────────────────────────────────────────────────────────────
-- phonepe_subscriptions had 9,668 dead tuples and no autovacuum had ever run:
-- at the default scale_factor of 0.2 the threshold is ~12k dead rows and rising
-- with the table. Pin it to a flat row count so vacuum/analyze keep pace with the
-- churn, and keep planner stats fresh for the partial indexes above.
ALTER TABLE phonepe_subscriptions SET (
    autovacuum_vacuum_scale_factor = 0.0,
    autovacuum_vacuum_threshold = 5000,
    autovacuum_analyze_scale_factor = 0.0,
    autovacuum_analyze_threshold = 2000
);
ALTER TABLE phonepe_subscriptions_archive SET (
    autovacuum_vacuum_scale_factor = 0.0,
    autovacuum_vacuum_threshold = 10000,
    autovacuum_analyze_scale_factor = 0.0,
    autovacuum_analyze_threshold = 5000
);

ANALYZE phonepe_subscriptions;
ANALYZE phonepe_subscriptions_archive;
ANALYZE phonepe_scheduled_transactions;
ANALYZE phonepe_subscription_transactions;
