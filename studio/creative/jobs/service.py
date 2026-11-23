from __future__ import annotations

import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creative.auth.service import AppRole, Principal, Role
from creative.config import Settings
from creative.db.tables import App, AppMember, Job, Template, User
from creative.errors import NotFoundError, UnavailableError, ValidationFailed
from creative.jobs.repository import JobFilter, JobRepository
from creative.providers.base import GenerationRequest, MediaType, UnsupportedRequestError
from creative.providers.registry import NoProviderAvailableError, ProviderRegistry


class GenerationService:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        repo: JobRepository,
        registry: ProviderRegistry,
    ):
        self.settings = settings
        self.db = sessions
        self.repo = repo
        self.registry = registry

    async def create(self, actor: User, app_id: UUID, body) -> Job:
        """A free-prompt test job inside an app (editors)."""
        media = MediaType(body.media_type)
        try:
            resolved = self.registry.resolve(media, body.provider, body.model)
        except NoProviderAvailableError as e:
            raise UnavailableError(str(e)) from e
        except UnsupportedRequestError as e:
            raise ValidationFailed(e.message, e.field) from e
        req = GenerationRequest(
            job_id="probe",
            prompt=body.prompt,
            media_type=media,
            model=resolved.model,
            aspect_ratio=body.aspect_ratio,
            n=body.n,
            duration_seconds=body.duration_seconds,
            negative_prompt=body.negative_prompt,
            seed=body.seed,
        )
        try:
            resolved.provider.validate(req)
        except UnsupportedRequestError as e:
            raise ValidationFailed(e.message, e.field) from e
        job = Job(
            id=uuid.uuid4(),
            status="queued",
            media_type=media.value,
            provider=resolved.provider.name,
            model=resolved.model,
            request={
                "prompt": body.prompt,
                "negative_prompt": body.negative_prompt,
                "aspect_ratio": body.aspect_ratio,
                "n": body.n,
                "duration_seconds": body.duration_seconds,
                "seed": body.seed,
            },
            webhook_url=str(body.webhook_url) if body.webhook_url else None,
            webhook_status="pending" if body.webhook_url else None,
            max_attempts=self.settings.job_max_attempts,
            created_by=actor.id,
            app_id=app_id,
        )
        await self.repo.create(job, [])
        return job

    # ---- reads with ownership ----------------------------------------------------------------
    async def role_in(self, p: Principal, app_id: UUID | None) -> AppRole | None:
        if p.role == Role.admin:
            return AppRole.admin
        if app_id is None:
            return None
        async with self.db() as s:
            r = await s.scalar(
                select(AppMember.role)
                .join(App, App.id == AppMember.app_id)
                .where(AppMember.app_id == app_id, AppMember.user_id == p.user.id, App.deleted_at.is_(None))
            )
        return AppRole[r] if r else None

    async def visible(self, p: Principal, job: Job | None) -> AppRole:
        """The viewer's role in the job's app, if they may see it: editors see the app's jobs,
        testers their own. Otherwise 404 (not 403), so job ids don't leak."""
        role = await self.role_in(p, job.app_id) if job else None
        if role is None or (role < AppRole.editor and job.created_by != p.user.id):
            raise NotFoundError("job not found")
        return role

    async def get_visible(self, p: Principal, job_id: UUID) -> tuple[Job, AppRole]:
        job = await self.repo.get(job_id)
        return job, await self.visible(p, job)

    async def list_in_app(self, p: Principal, role: AppRole, f: JobFilter) -> list[Job]:
        if role < AppRole.editor:
            f.created_by = p.user.id
        return await self.repo.list(f)

    # ---- responses ---------------------------------------------------------------------------
    async def to_responses(
        self, jobs: list[Job], viewer_role: AppRole | None, url_base: str = "/v1"
    ) -> list[dict]:
        """viewer_role None = webhook or app caller (shaped like a tester's view). `url_base` is
        where the caller fetches files: "/v1" for users, "/v1/app" for app keys."""
        ids = [j.id for j in jobs]
        assets = await self.repo.assets_for(ids)
        inputs = await self.repo.inputs_for(ids)
        user_ids = {j.created_by for j in jobs if j.created_by}
        template_ids = {j.template_id for j in jobs if j.template_id}
        app_ids = {j.app_id for j in jobs if j.app_id}
        async with self.db() as s:
            apps = (
                {a.id: a for a in await s.scalars(select(App).where(App.id.in_(app_ids)))} if app_ids else {}
            )
            users = (
                {u.id: u for u in await s.scalars(select(User).where(User.id.in_(user_ids)))}
                if user_ids
                else {}
            )
            templates = (
                {t.id: t for t in await s.scalars(select(Template).where(Template.id.in_(template_ids)))}
                if template_ids
                else {}
            )
        creator_view = viewer_role is not None and viewer_role >= AppRole.editor
        out = []
        for j in jobs:
            request = dict(j.request)
            if j.template_id and not creator_view:
                request.pop("prompt", None)
                request.pop("negative_prompt", None)
            t = templates.get(j.template_id) if j.template_id else None
            u = users.get(j.created_by) if j.created_by else None
            out.append(
                {
                    "id": j.id,
                    "status": j.status,
                    "media_type": j.media_type,
                    "provider": j.provider,
                    "model": j.model,
                    "request": request,
                    "template": (
                        {"id": t.id, "slug": t.slug, "title": t.title, "version": j.template_version}
                        if t
                        else None
                    ),
                    "inputs": [
                        {
                            "id": i.id,
                            "slot": i.slot,
                            "role": i.role,
                            "url": f"{url_base}/inputs/{i.id}",
                            "mime_type": i.mime_type,
                            "width": i.width,
                            "height": i.height,
                        }
                        for i in inputs.get(j.id, [])
                        if creator_view or i.role == "input"
                    ],
                    "assets": [
                        {
                            "id": a.id,
                            "url": f"{url_base}/assets/{a.id}",
                            "mime_type": a.mime_type,
                            "size_bytes": a.size_bytes,
                            "width": a.width,
                            "height": a.height,
                            "duration_seconds": a.duration_seconds,
                        }
                        for a in assets.get(j.id, [])
                    ],
                    "error": {"code": j.error_code, "message": j.error_message} if j.error_code else None,
                    "attempt": j.attempt,
                    "max_attempts": j.max_attempts,
                    "created_at": j.created_at,
                    "started_at": j.started_at,
                    "finished_at": j.finished_at,
                    "webhook": (
                        {"url": j.webhook_url, "status": j.webhook_status, "attempts": j.webhook_attempts}
                        if j.webhook_url
                        else None
                    ),
                    "created_by": {"id": u.id, "name": u.name} if u else None,
                    "app": (
                        {
                            "id": j.app_id,
                            "slug": apps[j.app_id].slug,
                            "name": apps[j.app_id].name,
                            "device_id": j.device_id if creator_view else None,
                        }
                        if j.app_id in apps
                        else None
                    ),
                }
            )
        return out

    async def payload_for_webhook(self, job_id: UUID) -> dict | None:
        job = await self.repo.get(job_id)
        if job is None:
            return None
        return (await self.to_responses([job], None))[0]
