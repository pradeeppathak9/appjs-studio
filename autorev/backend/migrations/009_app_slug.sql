-- App slug, like AppJs Studio: a unique, fixed machine name (3-64 lower-case letters, digits and
-- dashes) beside the editable display name. Existing apps get one derived from their name; a
-- duplicate or too-short result gets the first 8 characters of the app id appended. Re-runnable.
-- (New apps also get 16-char ids from here on; existing ids are not changed.)
--
--   docker compose exec backend python migrations/apply.py migrations/009_app_slug.sql

ALTER TABLE apps ADD COLUMN IF NOT EXISTS slug VARCHAR(64);

UPDATE apps
SET slug = left(trim(both '-' from regexp_replace(lower(name), '[^a-z0-9]+', '-', 'g')), 64)
WHERE slug IS NULL;

UPDATE apps SET slug = trim(both '-' from slug) WHERE slug LIKE '%-';

UPDATE apps a
SET slug = trim(both '-' from left(a.slug, 55)) || '-' || left(a.id, 8)
WHERE length(a.slug) < 3
   OR EXISTS (SELECT 1 FROM apps b WHERE b.slug = a.slug AND b.created_at < a.created_at);

UPDATE apps SET slug = 'app-' || left(id, 8) WHERE slug = '' OR slug LIKE '-%';

ALTER TABLE apps ALTER COLUMN slug SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_apps_slug ON apps (slug);
