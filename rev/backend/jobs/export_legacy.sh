#!/usr/bin/env bash
#
# export_legacy.sh — snapshot the phonepemicroservice DB for import into autorev.
#
# RUN THIS ON THE LEGACY DROPLET (the autorev host cannot reach that DB).
#
#   ./export_legacy.sh              # export from docker-compose.yaml's DATABASE_URL
#   DATABASE_URL=postgresql://...  ./export_legacy.sh
#   OUTDIR=/tmp/exp ./export_legacy.sh
#
# Produces <outdir>/legacy_export_<utc-timestamp>.tar.gz containing one CSV per
# table, a manifest, and SHA-256 sums. Read-only: it never writes to the DB.
#
# All tables are dumped in ONE repeatable-read transaction, so every CSV reflects
# the same instant even though the legacy workers keep writing. Without that the
# child tables could reference subscriptions the parent dump never saw.
#
set -euo pipefail

TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUTDIR="${OUTDIR:-$PWD/legacy_export_$TS}"
IMAGE="${IMAGE:-postgres:16-alpine}"
NETWORK="${NETWORK:-webservice-network}"

# Tables are dumped whole — no app_id filter. The legacy DB serves only postkaro,
# postshare and postkaro-test, and filtering the parent without filtering children
# by a join is how you end up with orphaned FKs. Select tenants at import instead.
TABLES=(subscriptions scheduled_transactions subscription_transactions subscription_archive webhook_logs)

if [[ -z "${DATABASE_URL:-}" ]]; then
  [[ -f docker-compose.yaml ]] || { echo "ERROR: no DATABASE_URL and no docker-compose.yaml here." >&2; exit 1; }
  DATABASE_URL="$(grep -oP 'DATABASE_URL=\K\S+' docker-compose.yaml | head -1)"
fi
# psql speaks postgresql://, not SQLAlchemy's +asyncpg dialect suffix.
DATABASE_URL="${DATABASE_URL/postgresql+asyncpg:/postgresql:}"
[[ -n "$DATABASE_URL" ]] || { echo "ERROR: could not determine DATABASE_URL." >&2; exit 1; }

mkdir -p "$OUTDIR"
echo "==> output: $OUTDIR"

# --user keeps the CSVs owned by you rather than the image's postgres uid.
run_psql() {
  docker run --rm --network "$NETWORK" --user "$(id -u):$(id -g)" \
    -v "$OUTDIR:/out" -e PGCONNECT_TIMEOUT=15 "$IMAGE" \
    psql "$DATABASE_URL" -v ON_ERROR_STOP=1 "$@"
}

echo "==> checking connectivity"
run_psql -Atc "SELECT 'connected to '||current_database()||' as '||current_user;"

echo "==> dumping ${#TABLES[@]} tables in a single consistent snapshot"
{
  echo "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;"
  for t in "${TABLES[@]}"; do
    # FORCE QUOTE * keeps JSONB and NULL unambiguous: NULL is bare, '' is "".
    echo "\\copy (SELECT * FROM $t) TO '/out/$t.csv' WITH (FORMAT csv, HEADER, FORCE_QUOTE *)"
  done
  echo "COMMIT;"
} | run_psql -q -f -

echo "==> building manifest"
run_psql -o /out/manifest.txt -c "
  SELECT now() AT TIME ZONE 'UTC' AS exported_at_utc,
         current_database() AS db,
         pg_size_pretty(pg_database_size(current_database())) AS db_total;
  SELECT relname,
         pg_size_pretty(pg_total_relation_size(relid)) AS total,
         pg_size_pretty(pg_relation_size(relid))       AS heap,
         pg_size_pretty(pg_indexes_size(relid))        AS indexes
  FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC;
  SELECT 'subscriptions' AS tbl, app_id, state, count(*) FROM subscriptions GROUP BY 1,2,3
  UNION ALL SELECT 'archive', app_id, state, count(*) FROM subscription_archive GROUP BY 1,2,3
  ORDER BY 1,2,3;
  SELECT 'scheduled_transactions' AS tbl, state, count(*) FROM scheduled_transactions GROUP BY 1,2
  UNION ALL SELECT 'subscription_transactions', state, count(*) FROM subscription_transactions GROUP BY 1,2
  ORDER BY 1,2;
  -- Gates the 'everything, lossy' decision: autorev has no pause_* columns, so a
  -- non-zero count here means paused mandates would lose their pause window.
  SELECT count(*) AS paused_or_pause_dated FROM subscriptions
   WHERE state = 'PAUSED' OR pause_start_date IS NOT NULL;
  -- The three Date columns that become epoch-ms on import.
  SELECT min(next_payment_date) AS min_npd, max(next_payment_date) AS max_npd FROM subscriptions;
  SELECT count(*) AS orphan_sched FROM scheduled_transactions s
   WHERE NOT EXISTS (SELECT 1 FROM subscriptions p WHERE p.id = s.subscription_id);
  SELECT count(*) AS orphan_txn FROM subscription_transactions t
   WHERE NOT EXISTS (SELECT 1 FROM subscriptions p WHERE p.id = t.subscription_id);
"

echo "==> row counts (CSV lines minus header)"
{
  echo "table,csv_data_rows"
  for t in "${TABLES[@]}"; do
    n=$(( $(wc -l < "$OUTDIR/$t.csv") - 1 ))
    printf '%s,%s\n' "$t" "$n"
    printf '  %-28s %10s rows  %8s\n' "$t" "$n" "$(du -h "$OUTDIR/$t.csv" | cut -f1)" >&2
  done
} > "$OUTDIR/rowcounts.csv"

echo "==> checksums"
( cd "$OUTDIR" && sha256sum ./*.csv manifest.txt > SHA256SUMS )

ARCHIVE="$OUTDIR/../legacy_export_$TS.tar.gz"
echo "==> packing"
tar -czf "$ARCHIVE" -C "$(dirname "$OUTDIR")" "$(basename "$OUTDIR")"
ARCHIVE="$(cd "$(dirname "$ARCHIVE")" && pwd)/$(basename "$ARCHIVE")"

echo
echo "Done."
echo "  archive : $ARCHIVE  ($(du -h "$ARCHIVE" | cut -f1))"
echo "  sha256  : $(sha256sum "$ARCHIVE" | cut -d' ' -f1)"
echo
echo "Copy it over with:"
echo "  scp <user>@<this-host>:$ARCHIVE ."
echo
echo "NOTE: subscription payload/response_payload and pause_* columns are exported in"
echo "full here even though the autorev import drops them — this archive is the only"
echo "copy once legacy is decommissioned."
echo
echo "HANDLE AS SENSITIVE: every row carries customer phone numbers, and the JSONB"
echo "payloads carry raw PhonePe request/response bodies. Move it over a private"
echo "channel and delete both copies once the import is reconciled."
