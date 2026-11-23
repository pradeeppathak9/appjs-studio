-- Outbound webhooks.
--
-- webhook_deliveries is created by Base.metadata.create_all() at backend
-- startup, constraint and indexes included, so this file only has to do what
-- create_all() will not: add columns to a table that already exists.
--
-- Every statement is idempotent, so the file can be re-run.
--
--   docker compose exec backend python migrations/apply.py migrations/003_webhooks.sql

ALTER TABLE apps ADD COLUMN IF NOT EXISTS webhook_url TEXT;
ALTER TABLE apps ADD COLUMN IF NOT EXISTS webhook_secret VARCHAR;
ALTER TABLE apps ADD COLUMN IF NOT EXISTS webhook_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE apps ADD COLUMN IF NOT EXISTS webhook_events JSONB;
