-- Optional Authorization header sent with webhook deliveries, for customer
-- endpoints that sit behind a bearer token or basic auth.
--
-- Idempotent, so the file can be re-run.
--
--   docker compose exec backend python migrations/apply.py migrations/004_webhook_auth_header.sql

ALTER TABLE apps ADD COLUMN IF NOT EXISTS webhook_auth_header TEXT;
ALTER TABLE apps ADD COLUMN IF NOT EXISTS webhook_auth_enabled BOOLEAN NOT NULL DEFAULT FALSE;
