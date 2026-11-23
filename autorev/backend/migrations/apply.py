"""Apply a .sql migration against AUTOREV_DATABASE_URL.

There is no Alembic in this project — the schema is created by
Base.metadata.create_all() and migrations are plain SQL applied once by hand:

    docker compose exec backend python migrations/apply.py migrations/001_indexes.sql

Statements run in AUTOCOMMIT because CREATE/DROP INDEX CONCURRENTLY cannot run
inside a transaction block. Each statement is reported with its duration, and a
failure is logged and skipped rather than aborting the run, so a partially
applied file can simply be re-run — every statement in 001_indexes.sql is
idempotent (IF NOT EXISTS / IF EXISTS).
"""
import os
import sys
import time

# Python puts this script's own directory on sys.path, not the app root above it.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine


def split_statements(sql: str) -> list[str]:
    lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def main(path: str) -> int:
    stmts = split_statements(open(path).read())
    print(f"{path}: {len(stmts)} statements\n")

    raw = engine.raw_connection()
    raw.set_isolation_level(0)  # AUTOCOMMIT
    cur = raw.cursor()
    failures = 0
    try:
        for st in stmts:
            label = " ".join(st.split())[:100]
            t0 = time.time()
            try:
                cur.execute(st)
                print(f"  OK   {time.time() - t0:6.2f}s  {label}")
            except Exception as e:
                failures += 1
                print(f"  FAIL {time.time() - t0:6.2f}s  {label}\n       {type(e).__name__}: {e}")
    finally:
        cur.close()
        raw.close()

    print(f"\n{len(stmts) - failures}/{len(stmts)} applied, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
