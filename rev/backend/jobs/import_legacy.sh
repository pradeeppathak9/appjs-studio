#!/usr/bin/env bash
#
# import_legacy.sh — load an export_legacy.sh snapshot into autorev.
#
#   ./import_legacy.sh --dry-run <export-dir>    # load, verify, ROLLBACK
#   ./import_legacy.sh --commit  <export-dir>    # load, verify, COMMIT
#
# Scope (per the migration decision): subscriptions, scheduled_transactions,
# subscription_transactions and subscription_archive. webhook_logs is NOT imported,
# and the columns autorev has no home for are dropped: payload, response_payload
# (on subscriptions/archive only — the transaction-level ones DO migrate),
# pause_start_date, pause_end_date, updated_at.
#
# Everything runs in ONE transaction, so a failure anywhere leaves the live tables
# untouched. --dry-run does the full load and all checks, then rolls back.
#
# Deviation from the plan: this is SQL/COPY rather than the planned Python job.
# ~1.02M rows row-by-row through an ORM would take hours; staged COPY plus
# INSERT..SELECT does the conversions server-side in minutes.
#
set -euo pipefail

MODE="${1:-}"; DIR="${2:-}"
[[ "$MODE" == "--dry-run" || "$MODE" == "--commit" ]] || { echo "usage: $0 --dry-run|--commit <export-dir>" >&2; exit 1; }
[[ -d "$DIR" ]] || { echo "ERROR: no such export dir: $DIR" >&2; exit 1; }
DIR="$(cd "$DIR" && pwd)"

: "${AUTOREV_DATABASE_URL:?set AUTOREV_DATABASE_URL (e.g. 'set -a; . ./.env; set +a')}"

# legacy app_id -> autorev apps.id. Any other app_id in the export aborts the run
# rather than being silently imported under the wrong tenant.
PK_ID="73c010725e3045ad8872979b510f5a65"   # POSTKAROONLINE
PS_ID="ef42c5da2db94eaaa709dbec15264184"   # POLITICONLINE-Post Share

for f in subscriptions scheduled_transactions subscription_transactions subscription_archive; do
  [[ -f "$DIR/$f.csv" ]] || { echo "ERROR: missing $DIR/$f.csv" >&2; exit 1; }
done

FINAL="ROLLBACK"; [[ "$MODE" == "--commit" ]] && FINAL="COMMIT"
echo "==> mode=$MODE  final=$FINAL"
echo "==> export=$DIR"

SQL=$(mktemp); trap 'rm -f "$SQL"' EXIT
cat > "$SQL" <<SQLEOF
\\set ON_ERROR_STOP on
\\timing on
BEGIN;

-- Staging mirrors the legacy CSV column order exactly (export used SELECT *).
-- UNLOGGED: staging never needs to survive a crash, and it keeps WAL for the
-- 1.02M staged rows off the wire.
CREATE UNLOGGED TABLE _mig_subs (
  id text, app_id text, phone_number text, amount int, max_amount int,
  amount_type text, frequency text, auth_workflow_type text, expire_at bigint,
  product_type text, payload jsonb, trail_days int, state text,
  pause_start_date bigint, pause_end_date bigint,
  phonepe_subscription_id text, phonepe_order_id text,
  created_at timestamptz, updated_at timestamptz, next_payment_date date,
  response_payload jsonb, last_payment_status text, total_payments int);
CREATE UNLOGGED TABLE _mig_sched (
  id text, subscription_id text, payment_date date, amount int, state text,
  attempts int, created_at timestamptz, updated_at timestamptz);
CREATE UNLOGGED TABLE _mig_txn (
  id text, subscription_id text, amount int, state text,
  created_at timestamptz, updated_at timestamptz, request_payload jsonb,
  response_payload jsonb, payment_due_date date, transaction_id text,
  scheduled_transaction_id text);
CREATE UNLOGGED TABLE _mig_arch (
  id text, app_id text, phone_number text, amount int, max_amount int,
  amount_type text, frequency text, auth_workflow_type text, expire_at bigint,
  product_type text, payload jsonb, trail_days int, state text,
  pause_start_date bigint, pause_end_date bigint, response_payload jsonb,
  phonepe_subscription_id text, phonepe_order_id text, next_payment_date date,
  last_payment_status text, created_at timestamptz, updated_at timestamptz,
  archived_at timestamptz);

\\copy _mig_subs  FROM '$DIR/subscriptions.csv'              WITH (FORMAT csv, HEADER)
\\copy _mig_sched FROM '$DIR/scheduled_transactions.csv'     WITH (FORMAT csv, HEADER)
\\copy _mig_txn   FROM '$DIR/subscription_transactions.csv'  WITH (FORMAT csv, HEADER)
\\copy _mig_arch  FROM '$DIR/subscription_archive.csv'       WITH (FORMAT csv, HEADER)

\\echo '== staged =='
SELECT '_mig_subs' t, count(*) FROM _mig_subs
UNION ALL SELECT '_mig_sched', count(*) FROM _mig_sched
UNION ALL SELECT '_mig_txn',   count(*) FROM _mig_txn
UNION ALL SELECT '_mig_arch',  count(*) FROM _mig_arch ORDER BY 1;

-- ── Guards: abort rather than import something wrong ────────────────────────
\\echo '== guard: unexpected app_id =='
DO \$\$
DECLARE bad text;
BEGIN
  SELECT string_agg(DISTINCT app_id, ', ') INTO bad FROM (
    SELECT app_id FROM _mig_subs UNION SELECT app_id FROM _mig_arch) x
  WHERE app_id NOT IN ('postkaro','postshare');
  IF bad IS NOT NULL THEN
    RAISE EXCEPTION 'unmapped legacy app_id(s): %  — add a mapping or filter them out', bad;
  END IF;
END \$\$;

-- Already-imported ids are skipped by ON CONFLICT DO NOTHING, which is what makes
-- a top-up run (a fresh export after a first import) safe. Report them rather than
-- aborting: 0 on a first run, non-zero on a re-run, both legitimate.
\\echo '== info: ids already present in autorev (skipped on insert) =='
SELECT 'subscriptions' t, count(*) FROM _mig_subs m JOIN phonepe_subscriptions p ON p.id = m.id
UNION ALL SELECT 'scheduled', count(*) FROM _mig_sched m JOIN phonepe_scheduled_transactions p ON p.id = m.id
UNION ALL SELECT 'transactions', count(*) FROM _mig_txn m JOIN phonepe_subscription_transactions p ON p.id = m.id
UNION ALL SELECT 'archive', count(*) FROM _mig_arch m JOIN phonepe_subscriptions_archive p ON p.id = m.id
ORDER BY 1;

-- The real FK hazard: a child about to be inserted whose parent is neither in this
-- export nor already in autorev. Checking staging alone would false-alarm on a
-- top-up run, where parents legitimately live only in the live table.
\\echo '== guard: children with no parent in export OR in autorev =='
DO \$\$
DECLARE n bigint;
BEGIN
  SELECT count(*) INTO n FROM _mig_sched s
   WHERE NOT EXISTS (SELECT 1 FROM _mig_subs p WHERE p.id = s.subscription_id)
     AND NOT EXISTS (SELECT 1 FROM phonepe_subscriptions p WHERE p.id = s.subscription_id);
  IF n > 0 THEN RAISE EXCEPTION 'scheduled_transactions with no resolvable parent: %', n; END IF;
  SELECT count(*) INTO n FROM _mig_txn t
   WHERE NOT EXISTS (SELECT 1 FROM _mig_subs p WHERE p.id = t.subscription_id)
     AND NOT EXISTS (SELECT 1 FROM phonepe_subscriptions p WHERE p.id = t.subscription_id);
  IF n > 0 THEN RAISE EXCEPTION 'subscription_transactions with no resolvable parent: %', n; END IF;
  SELECT count(*) INTO n FROM _mig_txn t WHERE t.scheduled_transaction_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM _mig_sched p WHERE p.id = t.scheduled_transaction_id)
   AND NOT EXISTS (SELECT 1 FROM phonepe_scheduled_transactions p WHERE p.id = t.scheduled_transaction_id);
  IF n > 0 THEN RAISE EXCEPTION 'transactions pointing at an unresolvable scheduled row: %', n; END IF;
END \$\$;

-- ── Insert, parents first (txn FKs both subs and sched) ─────────────────────
-- Date -> epoch ms at UTC midnight, matching workers/phone_worker_helper.py
-- _date_to_epoch_ms. NOT IST: the worker compares against an IST-derived
-- _today_end_ms(), and a 5h30m skew would shift every due date by a day.
\\echo '== insert: phonepe_subscriptions =='
INSERT INTO phonepe_subscriptions (
  id, app_id, phone_number, amount, max_amount, amount_type, frequency,
  auth_workflow_type, product_type, state, phonepe_subscription_id,
  phonepe_order_id, next_payment_date, last_payment_status, total_payments,
  trail_days, expire_at, created_at)
SELECT m.id,
       CASE m.app_id WHEN 'postkaro' THEN '$PK_ID' WHEN 'postshare' THEN '$PS_ID' END,
       m.phone_number, m.amount, m.max_amount, m.amount_type, m.frequency,
       m.auth_workflow_type, m.product_type, m.state, m.phonepe_subscription_id,
       m.phonepe_order_id,
       (EXTRACT(EPOCH FROM (m.next_payment_date::timestamp AT TIME ZONE 'UTC')) * 1000)::bigint,
       m.last_payment_status, COALESCE(m.total_payments, 0),
       COALESCE(m.trail_days, 0), m.expire_at, m.created_at
FROM _mig_subs m
ON CONFLICT (id) DO NOTHING;

\\echo '== insert: phonepe_scheduled_transactions =='
INSERT INTO phonepe_scheduled_transactions (
  id, subscription_id, payment_date, amount, state, attempts, created_at)
SELECT m.id, m.subscription_id,
       (EXTRACT(EPOCH FROM (m.payment_date::timestamp AT TIME ZONE 'UTC')) * 1000)::bigint,
       m.amount, m.state, COALESCE(m.attempts, 0), m.created_at
FROM _mig_sched m
ON CONFLICT (id) DO NOTHING;

\\echo '== insert: phonepe_subscription_transactions =='
INSERT INTO phonepe_subscription_transactions (
  id, subscription_id, scheduled_transaction_id, amount, state,
  payment_due_date, transaction_id, request_payload, response_payload, created_at)
SELECT m.id, m.subscription_id, m.scheduled_transaction_id, m.amount, m.state,
       (EXTRACT(EPOCH FROM (m.payment_due_date::timestamp AT TIME ZONE 'UTC')) * 1000)::bigint,
       m.transaction_id, m.request_payload, m.response_payload, m.created_at
FROM _mig_txn m
ON CONFLICT (id) DO NOTHING;

-- Legacy's archive has no total_payments column; autorev's does. Every archived
-- row is FAILED, so 0 is correct-by-construction, not a guess.
\\echo '== insert: phonepe_subscriptions_archive =='
INSERT INTO phonepe_subscriptions_archive (
  id, app_id, phone_number, amount, max_amount, amount_type, frequency,
  auth_workflow_type, product_type, state, phonepe_subscription_id,
  phonepe_order_id, next_payment_date, last_payment_status, total_payments,
  trail_days, expire_at, created_at, archived_at)
SELECT m.id,
       CASE m.app_id WHEN 'postkaro' THEN '$PK_ID' WHEN 'postshare' THEN '$PS_ID' END,
       m.phone_number, m.amount, m.max_amount, m.amount_type, m.frequency,
       m.auth_workflow_type, m.product_type, m.state, m.phonepe_subscription_id,
       m.phonepe_order_id,
       (EXTRACT(EPOCH FROM (m.next_payment_date::timestamp AT TIME ZONE 'UTC')) * 1000)::bigint,
       m.last_payment_status, 0,
       COALESCE(m.trail_days, 0), m.expire_at, m.created_at, m.archived_at
FROM _mig_arch m
ON CONFLICT (id) DO NOTHING;

-- ── Post-insert verification, inside the same transaction ───────────────────
\\echo '== verify: rows now in autorev for the two tenants =='
SELECT a.name, s.state, count(*)
FROM phonepe_subscriptions s JOIN apps a ON a.id = s.app_id
WHERE s.app_id IN ('$PK_ID','$PS_ID') GROUP BY 1,2 ORDER BY 1,2;

SELECT 'subscriptions' t, count(*) FROM phonepe_subscriptions WHERE app_id IN ('$PK_ID','$PS_ID')
UNION ALL SELECT 'archive', count(*) FROM phonepe_subscriptions_archive WHERE app_id IN ('$PK_ID','$PS_ID')
UNION ALL SELECT 'scheduled', count(*) FROM phonepe_scheduled_transactions sc
  WHERE EXISTS (SELECT 1 FROM phonepe_subscriptions s WHERE s.id = sc.subscription_id AND s.app_id IN ('$PK_ID','$PS_ID'))
UNION ALL SELECT 'transactions', count(*) FROM phonepe_subscription_transactions tx
  WHERE EXISTS (SELECT 1 FROM phonepe_subscriptions s WHERE s.id = tx.subscription_id AND s.app_id IN ('$PK_ID','$PS_ID'))
ORDER BY 1;

\\echo '== verify: date conversion round-trips (sample 5) =='
SELECT m.id, m.next_payment_date AS legacy_date,
       to_char(to_timestamp(s.next_payment_date/1000) AT TIME ZONE 'UTC','YYYY-MM-DD') AS autorev_date,
       m.next_payment_date::text = to_char(to_timestamp(s.next_payment_date/1000) AT TIME ZONE 'UTC','YYYY-MM-DD') AS ok
FROM _mig_subs m JOIN phonepe_subscriptions s ON s.id = m.id
WHERE m.next_payment_date IS NOT NULL LIMIT 5;

\\echo '== verify: any date that did NOT round-trip (must be 0) =='
SELECT count(*) AS bad_dates
FROM _mig_subs m JOIN phonepe_subscriptions s ON s.id = m.id
WHERE m.next_payment_date IS DISTINCT FROM
      (to_timestamp(s.next_payment_date/1000) AT TIME ZONE 'UTC')::date;

DROP TABLE _mig_subs, _mig_sched, _mig_txn, _mig_arch;
$FINAL;
SQLEOF

docker run --rm --network autorev-network --user "$(id -u):$(id -g)" \
  -v "$DIR:$DIR:ro" -v "$SQL:/mig.sql:ro" -e PGCONNECT_TIMEOUT=15 \
  postgres:16-alpine psql "$AUTOREV_DATABASE_URL" -f /mig.sql

echo
echo "==> finished with $FINAL"
[[ "$FINAL" == "ROLLBACK" ]] && echo "    Nothing was written. Re-run with --commit when the numbers look right."
