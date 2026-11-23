"""The credit ledger. Every change to an app user's balance is one `credit_ledger` row with a unique
idempotency key, and `app_users.credits` is updated in the same transaction. Callers pass their
open session so a charge commits (or rolls back) together with the job it pays for."""

from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from creative.db.tables import AppUser, CreditEntry
from creative.errors import InsufficientCredits

# Refund every given job that ended `failed` after being charged. Runs in the transaction that
# marks the jobs failed; the idempotency key makes a second run (or a second path) a no-op.
REFUND_FAILED_SQL = text(
    """
    WITH refunded AS (
        INSERT INTO credit_ledger (id, app_id, app_user_id, delta, reason, job_id, idempotency_key)
        SELECT gen_random_uuid(), j.app_id, j.app_user_id, j.credits_charged, 'refund', j.id,
               'refund:' || j.id
        FROM jobs j
        WHERE j.id = ANY(CAST(:ids AS uuid[])) AND j.status = 'failed'
          AND j.credits_charged > 0 AND j.app_user_id IS NOT NULL AND j.app_id IS NOT NULL
        ON CONFLICT (idempotency_key) DO NOTHING
        RETURNING app_user_id, delta
    )
    UPDATE app_users u SET credits = u.credits + r.total
    FROM (SELECT app_user_id, sum(delta) AS total FROM refunded GROUP BY app_user_id) r
    WHERE u.id = r.app_user_id
    """
)


async def refund_failed(s: AsyncSession, job_ids: list[UUID]) -> None:
    if job_ids:
        await s.execute(REFUND_FAILED_SQL, {"ids": list(job_ids)})


async def apply_entry(
    s: AsyncSession,
    *,
    app_id: UUID,
    app_user_id: UUID,
    delta: int,
    reason: str,
    key: str,
    job_id: UUID | None = None,
    subscription_id: UUID | None = None,
    note: str | None = None,
    created_by: UUID | None = None,
) -> bool:
    """Record one ledger entry and move the balance. False (and no change) if `key` was used before.
    A balance that would go below zero fails the `credits >= 0` check and rolls the transaction back;
    debits should call `lock_balance` first to fail with a clear error instead."""
    inserted = await s.scalar(
        insert(CreditEntry)
        .values(
            id=uuid.uuid4(),
            app_id=app_id,
            app_user_id=app_user_id,
            delta=delta,
            reason=reason,
            job_id=job_id,
            subscription_id=subscription_id,
            note=note,
            created_by=created_by,
            idempotency_key=key,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(CreditEntry.id)
    )
    if inserted is None:
        return False
    await s.execute(update(AppUser).where(AppUser.id == app_user_id).values(credits=AppUser.credits + delta))
    return True


async def lock_balance(s: AsyncSession, app_user_id: UUID, need: int) -> int:
    """Lock the user's row for this transaction and check they have `need` credits."""
    balance = await s.scalar(select(AppUser.credits).where(AppUser.id == app_user_id).with_for_update())
    if balance is None:
        raise InsufficientCredits("this account no longer exists")
    if balance < need:
        raise InsufficientCredits(
            f"this needs {need} credits and the account has {balance}",
            details=[{"credits": balance, "required": need}],
        )
    return balance
