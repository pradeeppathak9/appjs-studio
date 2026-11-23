import asyncio
import uuid

from sqlalchemy import text

from creative.db.tables import Asset, Job
from creative.jobs.repository import Lease
from creative.main import make_worker
from tests.conftest import run_worker_once


async def add_job(state, prompt="a red bicycle", **request) -> Job:
    job = Job(
        id=uuid.uuid4(),
        status="queued",
        media_type=request.pop("media_type", "image"),
        provider="fake",
        model="fake-image-1",
        request={"prompt": prompt, "n": 1, "aspect_ratio": "1:1", **request},
        max_attempts=request.pop("max_attempts", 3),
    )
    await state.repo.create(job, [])
    return job


async def test_concurrent_claims_never_return_the_same_job(state):
    for i in range(10):
        await add_job(state, f"job {i}")
    claims = await asyncio.gather(*(state.queue.claim(f"w{i}") for i in range(15)))
    ids = [j.id for j in claims if j is not None]
    assert len(ids) == 10 == len(set(ids))


async def test_claim_sets_a_fresh_heartbeat_so_a_retry_is_not_swept(state):
    job = await add_job(state)
    first = await state.queue.claim("A")
    async with state.engine.begin() as c:  # attempt 1 went stale long ago, then was released for retry
        await c.execute(
            text("UPDATE jobs SET heartbeat_at = now() - interval '1 hour' WHERE id = :id"), {"id": job.id}
        )
    assert await state.queue.release(Lease(job.id, "A", first.attempt), 0, "provider_unavailable", "x")
    retry = await state.queue.claim("B")
    requeued, failed = await state.queue.requeue_stale(120)
    assert job.id not in requeued + failed
    assert (await state.repo.get(job.id)).worker_id == "B" and retry.attempt == 2


async def test_stale_jobs_are_requeued_then_failed_at_max_attempts(state):
    job = await add_job(state, max_attempts=1)
    await state.queue.claim("A")
    async with state.engine.begin() as c:
        await c.execute(text("UPDATE jobs SET heartbeat_at = now() - interval '10 minutes'"))
    requeued, failed = await state.queue.requeue_stale(120)
    assert failed == [job.id]
    j = await state.repo.get(job.id)
    assert j.status == "failed" and j.error_code == "worker_lost"


async def test_a_fenced_out_worker_cannot_finish_a_taken_over_job(state):
    job = await add_job(state)
    a = await state.queue.claim("A")
    async with state.engine.begin() as c:
        await c.execute(text("UPDATE jobs SET heartbeat_at = now() - interval '10 minutes'"))
    await state.queue.requeue_stale(120)
    b = await state.queue.claim("B")
    asset = Asset(id=uuid.uuid4(), job_id=job.id, idx=0, path="x", mime_type="image/png", size_bytes=1)
    assert not await state.queue.mark_succeeded(Lease(job.id, "A", a.attempt), [asset])
    assert not await state.queue.mark_failed(Lease(job.id, "A", a.attempt), "x", "y")
    assert (await state.repo.get(job.id)).status == "running"
    assert await state.queue.mark_succeeded(Lease(job.id, "B", b.attempt), [])


async def test_worker_runs_a_job_to_success(state):
    job = await add_job(state, n=2)
    assert await run_worker_once(state)
    j = await state.repo.get(job.id)
    assert j.status == "succeeded" and j.attempt == 1
    assets = (await state.repo.assets_for([job.id]))[job.id]
    assert [a.idx for a in assets] == [0, 1]
    assert all(state.store.local_path(a.path).is_file() for a in assets)


async def test_transient_failures_are_retried(state):
    job = await add_job(state, prompt="FAIL_TRANSIENT:1 cat")
    await run_worker_once(state)
    j = await state.repo.get(job.id)
    assert j.status == "queued" and j.error_code == "provider_unavailable"
    await run_worker_once(state)
    j = await state.repo.get(job.id)
    assert j.status == "succeeded" and j.attempt == 2 and j.error_code is None


async def test_transient_failures_stop_at_max_attempts(state):
    job = await add_job(state, prompt="FAIL_TRANSIENT always", max_attempts=2)
    while await run_worker_once(state):
        pass
    j = await state.repo.get(job.id)
    assert j.status == "failed" and j.attempt == 2 and j.error_code == "provider_unavailable"


async def test_policy_failures_are_not_retried(state):
    job = await add_job(state, prompt="FAIL_POLICY")
    await run_worker_once(state)
    j = await state.repo.get(job.id)
    assert j.status == "failed" and j.attempt == 1 and j.error_code == "content_policy"


async def test_timeouts_fail_the_job(state, settings):
    job = await add_job(state, prompt="SLEEP:5")
    worker = make_worker(state)
    worker.settings = settings.model_copy(update={"job_timeout_image_s": 0.2})
    await worker.run_once()
    j = await state.repo.get(job.id)
    assert j.status == "failed" and j.error_code == "timeout"


async def test_video_job(state):
    job = await add_job(state, media_type="video", aspect_ratio="16:9", duration_seconds=2)
    await run_worker_once(state)
    j = await state.repo.get(job.id)
    assert j.status == "succeeded"
    (asset,) = (await state.repo.assets_for([job.id]))[job.id]
    assert asset.duration_seconds == 2


async def test_worker_loop_wakes_on_notify_and_stops_cleanly(state, settings):
    worker = make_worker(state)
    worker.settings = settings.model_copy(update={"worker_poll_interval_s": 30})
    await worker.start()
    try:
        await asyncio.sleep(0.5)  # LISTEN connection up
        job = await add_job(state)
        for _ in range(50):
            if (await state.repo.get(job.id)).status == "succeeded":
                break
            await asyncio.sleep(0.1)
        assert (await state.repo.get(job.id)).status == "succeeded"  # well before the 30 s poll
    finally:
        await worker.stop()
    assert not [w for w in await state.queue.live_workers(120) if w["id"] == worker.id]


async def test_stopping_mid_job_releases_it(state, settings):
    worker = make_worker(state)
    worker.settings = settings.model_copy(update={"shutdown_grace_s": 0.2})
    job = await add_job(state, prompt="SLEEP:10")
    await worker.start()
    for _ in range(50):
        if (await state.repo.get(job.id)).status == "running":
            break
        await asyncio.sleep(0.1)
    await worker.stop()
    j = await state.repo.get(job.id)
    assert j.status == "queued" and j.error_code == "shutdown"
