-- An integration's own labels for a Razorpay subscription (e.g. AppJs Studio's app, plan and
-- order), set at /setup and added to the notes of its Razorpay customer, authorisation order
-- and every recurring charge, so the Razorpay dashboard shows which app a payment came from.
--
--   docker compose exec backend python migrations/apply.py migrations/008_razorpay_notes.sql

ALTER TABLE razorpay_subscriptions ADD COLUMN IF NOT EXISTS notes JSONB;
