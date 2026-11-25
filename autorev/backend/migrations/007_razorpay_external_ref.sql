-- An integration's own reference for a Razorpay subscription (e.g. AppJs Studio's
-- "studio:<order id>"), set at /setup and returned in status responses and every
-- outbound webhook, so the integration can match events without relying on the
-- phone number.
--
--   docker compose exec backend python migrations/apply.py migrations/007_razorpay_external_ref.sql

ALTER TABLE razorpay_subscriptions ADD COLUMN IF NOT EXISTS external_ref VARCHAR(200);

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_razorpay_subs_app_external_ref
  ON razorpay_subscriptions (app_id, external_ref)
  WHERE external_ref IS NOT NULL;
