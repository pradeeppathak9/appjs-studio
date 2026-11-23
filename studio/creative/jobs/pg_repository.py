from __future__ import annotations

from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creative.db.engine import NOTIFY_CHANNEL
from creative.db.tables import Asset, Job, JobInput, Worker
from creative.endusers.credits import apply_entry, lock_balance, refund_failed
from creative.jobs.repository import JobFilter, Lease

CLAIM_SQL = text(
    """
    UPDATE jobs SET status = 'running', worker_id = :worker_id, attempt = attempt + 1,
           started_at = now(), heartbeat_at = now(), updated_at = now(),
           error_code = NULL, error_message = NULL
    WHERE id = (
        SELECT id FROM jobs
        WHERE status = 'queued' AND run_after <= now()
        ORDER BY created_at
        LIMIT 1
        FOR UPDATE SKIP LOCKED
    )
    RETURNING id
    """
)

FENCE = "id = :job_id AND worker_id = :worker_id AND attempt = :attempt AND status = 'running'"

REQUEUE_STALE_SQL = text(
    """
    UPDATE jobs SET
        status = CASE WHEN attempt >= max_attempts THEN 'failed' ELSE 'queued' END,
        error_code = CASE WHEN attempt >= max_attempts THEN 'worker_lost' ELSE error_code END,
        error_message = CASE WHEN attempt >= max_attempts
                             THEN 'the worker running this job stopped responding' ELSE error_message END,
        finished_at = CASE WHEN attempt >= max_attempts THEN now() ELSE NULL END,
        worker_id = NULL, run_after = now(), updated_at = now()
    WHERE status = 'running' AND heartbeat_at < now() - make_interval(secs => :stale)
    RETURNING id, status
    """
)


def _lease_params(lease: Lease) -> dict:
    return {"job_id": lease.job_id, "worker_id": lease.worker_id, "attempt": lease.attempt}


class PgJobRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def create(self, job: Job, inputs: list[JobInput]) -> None:
        """Insert a queued job. A job with `credits_charged` debits its app user in the same
        transaction (InsufficientCredits, and no job, when they can't pay)."""
        charge = job.credits_charged if job.app_user_id else 0
        async with self.sessions.begin() as s:
            if charge:
                await lock_balance(s, job.app_user_id, charge)
            s.add(job)
            await s.flush()
            s.add_all(inputs)
            if charge:
                await apply_entry(
                    s,
                    app_id=job.app_id,
                    app_user_id=job.app_user_id,
                    delta=-charge,
                    reason="generation",
                    key=f"gen:{job.id}",
                    job_id=job.id,
                )
            await s.execute(text(f"NOTIFY {NOTIFY_CHANNEL}"))

    async def get(self, job_id: UUID) -> Job | None:
        async with self.sessions() as s:
            return await s.get(Job, job_id)

    async def list(self, f: JobFilter) -> list[Job]:
        q = select(Job).order_by(Job.created_at.desc()).limit(min(max(f.limit, 1), 200))
        if f.status:
            q = q.where(Job.status == f.status)
        if f.template_id:
            q = q.where(Job.template_id == f.template_id)
        if f.created_by:
            q = q.where(Job.created_by == f.created_by)
        if f.app_id:
            q = q.where(Job.app_id == f.app_id)
        if f.device_id:
            q = q.where(Job.device_id == f.device_id)
        if f.app_user_id:
            q = q.where(Job.app_user_id == f.app_user_id)
        async with self.sessions() as s:
            return list((await s.scalars(q)).all())

    async def assets_for(self, job_ids: list[UUID]) -> dict[UUID, list[Asset]]:
        out: dict[UUID, list[Asset]] = defaultdict(list)
        if job_ids:
            async with self.sessions() as s:
                rows = await s.scalars(select(Asset).where(Asset.job_id.in_(job_ids)).order_by(Asset.idx))
                for a in rows:
                    out[a.job_id].append(a)
        return out

    async def inputs_for(self, job_ids: list[UUID]) -> dict[UUID, list[JobInput]]:
        out: dict[UUID, list[JobInput]] = defaultdict(list)
        if job_ids:
            async with self.sessions() as s:
                q = select(JobInput).where(JobInput.job_id.in_(job_ids)).order_by(JobInput.created_at)
                for i in await s.scalars(q):
                    out[i.job_id].append(i)
        return out

    async def get_asset(self, asset_id: UUID) -> tuple[Asset, Job] | None:
        async with self.sessions() as s:
            row = (await s.execute(select(Asset, Job).join(Job).where(Asset.id == asset_id))).first()
            return (row[0], row[1]) if row else None

    async def get_input(self, input_id: UUID) -> tuple[JobInput, Job] | None:
        async with self.sessions() as s:
            row = (await s.execute(select(JobInput, Job).join(Job).where(JobInput.id == input_id))).first()
            return (row[0], row[1]) if row else None

    async def set_webhook(self, job_id: UUID, status: str, attempts: int) -> None:
        async with self.sessions.begin() as s:
            await s.execute(
                update(Job)
                .where(Job.id == job_id)
                .values(webhook_status=status, webhook_attempts=attempts, updated_at=func.now())
            )

    async def counts(self) -> dict[str, int]:
        async with self.sessions() as s:
            rows = await s.execute(
                select(Job.status, func.count())
                .where(Job.status.in_(["queued", "running"]))
                .group_by(Job.status)
            )
            counts = {"queued": 0, "running": 0}
            counts.update({status: n for status, n in rows})
            return counts


class PgJobQueue:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def claim(self, worker_id: str) -> Job | None:
        async with self.sessions.begin() as s:
            job_id = (await s.execute(CLAIM_SQL, {"worker_id": worker_id})).scalar()
            if job_id is None:
                return None
        async with self.sessions() as s:
            return await s.get(Job, job_id)

    async def mark_succeeded(self, lease: Lease, assets: list[Asset]) -> bool:
        async with self.sessions.begin() as s:
            done = await s.execute(
                text(
                    f"UPDATE jobs SET status='succeeded', finished_at=now(), updated_at=now(), "
                    f"heartbeat_at=now() WHERE {FENCE}"
                ),
                _lease_params(lease),
            )
            if done.rowcount != 1:
                return False
            s.add_all(assets)
        return True

    async def mark_failed(self, lease: Lease, code: str, message: str) -> bool:
        async with self.sessions.begin() as s:
            done = await s.execute(
                text(
                    f"UPDATE jobs SET status='failed', error_code=:code, error_message=:message, "
                    f"finished_at=now(), updated_at=now() WHERE {FENCE}"
                ),
                {**_lease_params(lease), "code": code, "message": message[:2000]},
            )
            if done.rowcount != 1:
                return False
            await refund_failed(s, [lease.job_id])
            return True

    async def release(self, lease: Lease, delay_s: float, code: str | None, message: str | None) -> bool:
        async with self.sessions.begin() as s:
            done = await s.execute(
                text(
                    f"UPDATE jobs SET status='queued', worker_id=NULL, "
                    f"run_after=now() + make_interval(secs => :delay), "
                    f"error_code=:code, error_message=:message, updated_at=now() WHERE {FENCE}"
                ),
                {**_lease_params(lease), "delay": delay_s, "code": code, "message": (message or "")[:2000]},
            )
            return done.rowcount == 1

    async def heartbeat(self, worker_id: str, hostname: str, inflight: int, leases: list[Lease]) -> None:
        async with self.sessions.begin() as s:
            await s.execute(
                text(
                    "INSERT INTO workers (id, hostname, inflight) VALUES (:id, :host, :inflight) "
                    "ON CONFLICT (id) DO UPDATE SET heartbeat_at = now(), inflight = :inflight"
                ),
                {"id": worker_id, "host": hostname, "inflight": inflight},
            )
            for lease in leases:
                await s.execute(
                    text(f"UPDATE jobs SET heartbeat_at=now() WHERE {FENCE}"), _lease_params(lease)
                )
            await s.execute(text("DELETE FROM workers WHERE heartbeat_at < now() - interval '1 hour'"))
            await s.execute(text("DELETE FROM login_attempts WHERE at < now() - interval '1 day'"))

    async def requeue_stale(self, stale_after_s: float) -> tuple[list[UUID], list[UUID]]:
        async with self.sessions.begin() as s:
            rows = (await s.execute(REQUEUE_STALE_SQL, {"stale": stale_after_s})).all()
            await refund_failed(s, [r.id for r in rows if r.status == "failed"])
        requeued = [r.id for r in rows if r.status == "queued"]
        failed = [r.id for r in rows if r.status == "failed"]
        return requeued, failed

    async def remove_worker(self, worker_id: str) -> None:
        async with self.sessions.begin() as s:
            await s.execute(text("DELETE FROM workers WHERE id = :id"), {"id": worker_id})

    async def live_workers(self, fresh_within_s: float) -> list[dict]:
        async with self.sessions() as s:
            rows = await s.scalars(select(Worker).order_by(Worker.started_at))
            now = (await s.execute(select(func.now()))).scalar_one()
            return [
                {
                    "id": w.id,
                    "hostname": w.hostname,
                    "heartbeat_at": w.heartbeat_at,
                    "inflight": w.inflight,
                    "fresh": (now - w.heartbeat_at).total_seconds() <= fresh_within_s,
                }
                for w in rows
            ]
