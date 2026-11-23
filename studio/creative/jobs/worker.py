from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import time
from uuid import UUID, uuid4

from creative.config import Settings
from creative.db.engine import NOTIFY_CHANNEL, listen_connection
from creative.db.tables import Asset, Job
from creative.jobs.repository import JobQueue, JobRepository, Lease
from creative.jobs.webhooks import WebhookSender
from creative.providers.base import (
    GenerationRequest,
    InputImage,
    MediaType,
    ProviderError,
    ProviderOperationTimeout,
)
from creative.providers.registry import ProviderRegistry
from creative.storage.base import AssetStore

log = logging.getLogger(__name__)

EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "video/quicktime": "mov",
}


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class Worker:
    def __init__(
        self,
        settings: Settings,
        queue: JobQueue,
        repo: JobRepository,
        store: AssetStore,
        registry: ProviderRegistry,
        webhooks: WebhookSender | None,
        wid: str | None = None,
        billing=None,  # creative.endusers.billing.BillingService: monthly subscription credits
    ):
        self.settings = settings
        self.queue = queue
        self.repo = repo
        self.store = store
        self.registry = registry
        self.webhooks = webhooks
        self.billing = billing
        self._last_billing_sweep = 0.0
        self.id = wid or worker_id()
        self.hostname = socket.gethostname()
        self.leases: dict[UUID, Lease] = {}
        self.tasks: dict[UUID, asyncio.Task] = {}
        self.background: set[asyncio.Task] = set()
        self.wake = asyncio.Event()
        self._stopping = False
        self._loops: list[asyncio.Task] = []

    # ---- lifecycle -------------------------------------------------------------------------
    async def start(self) -> None:
        if hasattr(self.store, "sweep_temp"):
            self.store.sweep_temp()
        await self.queue.heartbeat(self.id, self.hostname, 0, [])
        await self.queue.requeue_stale(self.settings.stale_job_after_s)
        self._loops = [
            asyncio.create_task(self._claim_loop(), name="worker-claim"),
            asyncio.create_task(self._heartbeat_loop(), name="worker-heartbeat"),
            asyncio.create_task(self._listen_loop(), name="worker-listen"),
        ]
        log.info("worker %s started (concurrency %d)", self.id, self.settings.worker_concurrency)

    async def stop(self) -> None:
        self._stopping = True
        for t in self._loops:
            t.cancel()
        await asyncio.gather(*self._loops, return_exceptions=True)
        if self.tasks:
            log.info(
                "worker %s waiting up to %ss for %d jobs",
                self.id,
                self.settings.shutdown_grace_s,
                len(self.tasks),
            )
            await asyncio.wait(list(self.tasks.values()), timeout=self.settings.shutdown_grace_s)
        for job_id, task in list(self.tasks.items()):
            task.cancel()
            lease = self.leases.get(job_id)
            if lease:
                await self.queue.release(lease, 0, "shutdown", "worker stopped before the job finished")
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        if self.background:
            await asyncio.wait(list(self.background), timeout=5)
        await self.queue.remove_worker(self.id)
        log.info("worker %s stopped", self.id)

    # ---- loops -------------------------------------------------------------------------------
    async def _claim_loop(self) -> None:
        while not self._stopping:
            claimed = False
            if len(self.tasks) < self.settings.worker_concurrency:
                try:
                    job = await self.queue.claim(self.id)
                except Exception as e:
                    # Usually the database is restarting; one line per try, and back off.
                    log.warning("claim failed (%s: %s); retrying in 2s", type(e).__name__, e)
                    await asyncio.sleep(2)
                    continue
                if job is not None:
                    claimed = True
                    self.leases[job.id] = Lease(job.id, self.id, job.attempt)
                    task = asyncio.create_task(self._execute(job), name=f"job-{job.id}")
                    self.tasks[job.id] = task
                    task.add_done_callback(lambda _t, jid=job.id: self._done(jid))
            if not claimed:
                self.wake.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.wake.wait(), self.settings.worker_poll_interval_s)

    def _done(self, job_id: UUID) -> None:
        self.tasks.pop(job_id, None)
        self.leases.pop(job_id, None)
        self.wake.set()

    async def _heartbeat_loop(self) -> None:
        while not self._stopping:
            await asyncio.sleep(self.settings.worker_heartbeat_s)
            try:
                await self.queue.heartbeat(
                    self.id, self.hostname, len(self.tasks), list(self.leases.values())
                )
                requeued, failed = await self.queue.requeue_stale(self.settings.stale_job_after_s)
                if requeued or failed:
                    log.warning("stale jobs: requeued %s, failed %s", requeued, failed)
                    self.wake.set()
            except Exception:
                log.exception("heartbeat failed")
            await self.billing_sweep()

    async def billing_sweep(self, force: bool = False) -> None:
        """Monthly subscription credits, at most once a minute per worker (idempotent across workers)."""
        if self.billing is None:
            return
        now = time.monotonic()
        if not force and now - self._last_billing_sweep < 60:
            return
        self._last_billing_sweep = now
        try:
            await self.billing.grant_due_credits()
        except Exception:
            log.exception("granting subscription credits failed")

    async def _listen_loop(self) -> None:
        while not self._stopping:
            conn = None
            try:
                conn = await listen_connection(self.settings)
                closed = asyncio.Event()
                conn.add_termination_listener(lambda _c, ev=closed: ev.set())
                await conn.add_listener(NOTIFY_CHANNEL, lambda *_: self.wake.set())
                await closed.wait()
                raise ConnectionError("LISTEN connection closed")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.info("LISTEN connection lost (%s); polling until it's back", e)
                await asyncio.sleep(5)
            finally:
                if conn is not None and not conn.is_closed():
                    with contextlib.suppress(Exception):
                        await conn.close()

    # ---- one job -----------------------------------------------------------------------------
    async def run_once(self) -> bool:
        """Claim and run one job to completion (tests)."""
        job = await self.queue.claim(self.id)
        if job is None:
            return False
        self.leases[job.id] = Lease(job.id, self.id, job.attempt)
        try:
            await self._execute(job)
        finally:
            self.leases.pop(job.id, None)
        return True

    async def _build_request(self, job: Job) -> GenerationRequest:
        r = job.request
        inputs = (await self.repo.inputs_for([job.id])).get(job.id, [])
        images = [
            InputImage(self.store.local_path(i.path), i.mime_type, i.width, i.height, i.role)
            for i in sorted(inputs, key=lambda i: (i.role != "input", i.created_at))
        ]
        return GenerationRequest(
            job_id=str(job.id),
            prompt=r["prompt"],
            media_type=MediaType(job.media_type),
            model=job.model,
            aspect_ratio=r.get("aspect_ratio"),
            n=r.get("n", 1),
            duration_seconds=r.get("duration_seconds"),
            negative_prompt=r.get("negative_prompt"),
            seed=r.get("seed"),
            input_images=images,
        )

    async def _execute(self, job: Job) -> None:
        lease = Lease(job.id, self.id, job.attempt)
        written: list[str] = []
        try:
            provider = self.registry.get(job.provider)
            if provider is None:
                raise ProviderError(
                    f"provider {job.provider} is not configured on this worker",
                    code="provider_not_configured",
                )
            req = await self._build_request(job)
            timeout = (
                self.settings.job_timeout_image_s
                if req.media_type == MediaType.IMAGE
                else self.settings.job_timeout_video_s
            )
            try:
                if req.media_type == MediaType.IMAGE:
                    results = await asyncio.wait_for(provider.generate_image(req), timeout)
                else:
                    results = [await asyncio.wait_for(provider.generate_video(req), timeout)]
            except TimeoutError as e:
                raise ProviderOperationTimeout(f"no result after {timeout:.0f}s") from e

            assets = []
            for idx, result in enumerate(results):
                ext = EXTENSIONS.get(result.mime_type, "bin")
                path, size = await self.store.put(str(job.id), f"{job.attempt}-{idx}", result.content, ext)
                written.append(path)
                assets.append(
                    Asset(
                        id=uuid4(),
                        job_id=job.id,
                        idx=idx,
                        path=path,
                        mime_type=result.mime_type,
                        size_bytes=size,
                        width=result.width,
                        height=result.height,
                        duration_seconds=result.duration_seconds,
                        metadata_=result.metadata,
                    )
                )
            if not await self.queue.mark_succeeded(lease, assets):
                log.warning("job %s was taken over before it finished; dropping its result", job.id)
                await self.store.delete_paths(written)
                return
            log.info("job %s succeeded with %d assets", job.id, len(assets))
            self._webhook(job)
        except asyncio.CancelledError:
            await self.store.delete_paths(written)
            raise
        except ProviderError as e:
            await self.store.delete_paths(written)
            if e.retryable and job.attempt < job.max_attempts:
                delay = self.settings.retry_backoff_base_s * 2 ** (job.attempt - 1)
                if await self.queue.release(lease, delay, e.code, e.message):
                    log.info(
                        "job %s attempt %d failed (%s); retry in %.0fs", job.id, job.attempt, e.code, delay
                    )
                    return
            if await self.queue.mark_failed(lease, e.code, e.message):
                log.info("job %s failed: %s", job.id, e.code)
                self._webhook(job)
        except Exception as e:
            log.exception("job %s crashed", job.id)
            await self.store.delete_paths(written)
            if await self.queue.mark_failed(lease, "internal_error", f"{type(e).__name__}: {e}"):
                self._webhook(job)

    def _webhook(self, job: Job) -> None:
        if not (self.webhooks and job.webhook_url):
            return
        task = asyncio.create_task(self.webhooks.send(job.id, job.webhook_url))
        self.background.add(task)
        task.add_done_callback(self.background.discard)
