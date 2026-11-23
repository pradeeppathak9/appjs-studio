-- Razorpay collection moves into AutoRev (workers/razorpay_worker_helper.py).
--
-- Each collection attempt records the due date it is paying for, so retries are
-- counted per billing cycle and a cycle is never collected twice. The partial
-- index serves the reconcile sweep, which only ever looks at unsettled rows.
--
--   docker compose exec backend python migrations/apply.py migrations/006_razorpay_collection.sql

ALTER TABLE razorpay_transactions ADD COLUMN IF NOT EXISTS payment_due_date BIGINT;

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_razorpay_txn_sub_due
  ON razorpay_transactions (subscription_id, payment_due_date);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_razorpay_txn_unsettled
  ON razorpay_transactions (created_at)
  WHERE state IN ('NOTIFIED', 'INITIATED');

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_razorpay_subs_active_next_payment
  ON razorpay_subscriptions (app_id, next_payment_date)
  WHERE state = 'ACTIVE';
