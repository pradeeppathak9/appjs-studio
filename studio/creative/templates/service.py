from __future__ import annotations

import uuid
from dataclasses import dataclass
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import String, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from creative.config import Settings
from creative.db.tables import AppUser, Job, JobInput, Template, TemplateEvent, TemplateVersion, Upload, User
from creative.errors import (
    ConflictError,
    ForbiddenError,
    InsufficientCredits,
    NotFoundError,
    SignInRequired,
    UnavailableError,
    ValidationFailed,
)
from creative.jobs.repository import JobRepository
from creative.media.images import ImageTooLarge, InvalidImage, normalize_image, read_upload
from creative.providers.base import GenerationRequest, InputImage, MediaType, UnsupportedRequestError
from creative.providers.registry import ProviderRegistry
from creative.storage.base import AssetStore
from creative.templates.models import TemplateCreate, TemplateFields, TemplateUpdate, Variable
from creative.templates.render import placeholders, render, resolve_values

VERSION_FIELDS = (
    "title",
    "description",
    "media_type",
    "provider",
    "model",
    "allowed_models",
    "prompt",
    "negative_prompt",
    "params",
    "inputs",
    "variables",
    "reference_uploads",
    "cover_upload",
    "note",
)


@dataclass
class TemplateView:
    template: Template
    version: TemplateVersion
    editor: User | None = None


def _version_row(template_id: UUID, version: int, f: TemplateFields, actor: User) -> TemplateVersion:
    return TemplateVersion(
        template_id=template_id,
        version=version,
        title=f.title.strip(),
        description=f.description,
        media_type=f.media_type,
        provider=f.provider,
        model=f.model,
        allowed_models=list(dict.fromkeys(f.allowed_models)),
        prompt=f.prompt,
        negative_prompt=f.negative_prompt or None,
        params=f.params.model_dump(),
        inputs=[s.model_dump() for s in f.inputs],
        variables=[v.model_dump() for v in f.variables],
        reference_uploads=[UUID(u) for u in f.reference_uploads],
        cover_upload=UUID(f.cover_upload) if f.cover_upload else None,
        note=f.note,
        created_by=actor.id,
    )


class TemplateService:
    def __init__(
        self,
        settings: Settings,
        sessions: async_sessionmaker[AsyncSession],
        registry: ProviderRegistry,
        store: AssetStore,
        jobs: JobRepository,
    ):
        self.settings = settings
        self.db = sessions
        self.registry = registry
        self.store = store
        self.jobs = jobs

    # ---- save-time checks ---------------------------------------------------------------------------
    async def check(self, f: TemplateFields, app_id: UUID) -> list[str]:
        """Raise ValidationFailed for errors; return warnings."""
        errors: list[dict] = []
        warnings: list[str] = []

        def err(field: str, message: str) -> None:
            errors.append({"field": field, "message": message})

        declared = [v.name for v in f.variables]
        if len(set(declared)) != len(declared):
            err("variables", "variable names must be unique")
        used = placeholders(f.prompt) + placeholders(f.negative_prompt)
        for name in used:
            if name not in declared:
                err("prompt", f"{{{{{name}}}}} is used but not declared as a variable")
        for name in declared:
            if name not in used:
                err(f"variables.{name}", "declared but not used in the prompt")
        slots = [s.name for s in f.inputs]
        if len(set(slots)) != len(slots):
            err("inputs", "input slot names must be unique")
        if f.media_type == "image" and f.params.duration_seconds is not None:
            err("params.duration_seconds", "only for video templates")
        if f.media_type == "video" and f.params.n != 1:
            err("params.n", "must be 1 for video")
        for v in f.variables:
            if v.choices and v.default and v.default not in v.choices:
                err(f"variables.{v.name}.default", "must be one of the choices")
            if len(v.default) > v.max_length:
                err(f"variables.{v.name}.default", "longer than max_length")
        wanted = {("reference_uploads", u) for u in f.reference_uploads}
        if f.cover_upload:
            wanted.add(("cover_upload", f.cover_upload))
        if wanted:
            try:
                ids = {UUID(u) for _, u in wanted}
            except ValueError:
                ids = set()
                err("reference_uploads", "upload ids must be UUIDs")
            async with self.db() as s:
                # uploads of this app, or older ones made before uploads belonged to apps
                found = {
                    str(x)
                    for x in await s.scalars(
                        select(Upload.id).where(
                            Upload.id.in_(ids), (Upload.app_id == app_id) | Upload.app_id.is_(None)
                        )
                    )
                }
            for field, u in sorted(wanted):
                if ids and u not in found:
                    err(field, f"upload {u} not found")

        provider = self.registry.get(f.provider)
        if provider is None:
            warnings.append(
                f"provider {f.provider!r} is not configured on this server; the template can be saved "
                "but calls will fail until it is"
            )
        else:
            caps = provider.capabilities
            if not getattr(caps, f.media_type):
                err("media_type", f"{f.provider} does not generate {f.media_type}")
            image_count = len(f.inputs) + len(f.reference_uploads)
            if image_count and not caps.image_input:
                err("provider", f"{f.provider} does not take input images")
            elif image_count > caps.max_input_images:
                err(
                    "inputs",
                    f"{f.provider} takes at most {caps.max_input_images} images (slots + references)",
                )
            if f.media_type == "image":
                if f.params.n > caps.max_images:
                    err("params.n", f"at most {caps.max_images} for {f.provider}")
                ratios = caps.image_aspect_ratios
            else:
                ratios = caps.video_aspect_ratios
                d = f.params.duration_seconds
                if d is not None and caps.video_durations and d not in caps.video_durations:
                    err(
                        "params.duration_seconds",
                        f"must be one of {', '.join(map(str, caps.video_durations))}",
                    )
            if f.params.aspect_ratio != "auto" and f.params.aspect_ratio not in ratios:
                err("params.aspect_ratio", f"must be auto or one of {', '.join(ratios)}")
            if f.params.seed is not None and not caps.supports_seed:
                err("params.seed", f"{f.provider} does not support seed")
            for m in [f.model, *f.allowed_models]:
                known = (
                    caps.image_input_models
                    if image_count
                    else (caps.known_image_models if f.media_type == "image" else caps.known_video_models)
                )
                if known and m not in known:
                    warnings.append(
                        f"model {m!r} is not in {f.provider}'s known list for this kind of template"
                    )
        if errors:
            raise ValidationFailed("the template has errors", details=errors)
        return warnings

    # ---- reads --------------------------------------------------------------------------------
    async def _find(self, s: AsyncSession, app_id: UUID, ref: str) -> Template | None:
        """A live (not deleted) template of this app, by id or slug."""
        q = select(Template).where(Template.app_id == app_id, Template.deleted_at.is_(None))
        try:
            q = q.where(Template.id == UUID(ref))
        except ValueError:
            q = q.where(Template.slug == ref)
        return await s.scalar(q)

    async def get(
        self, app_id: UUID, ref: str, version: int | None = None, *, active_only: bool = False
    ) -> TemplateView:
        async with self.db() as s:
            t = await self._find(s, app_id, ref)
            if t is None or (active_only and t.status != "active"):
                raise NotFoundError("template not found")
            v = await s.get(TemplateVersion, (t.id, version or t.current_version))
            if v is None:
                raise NotFoundError("version not found")
            editor = await s.get(User, v.created_by)
            return TemplateView(t, v, editor)

    async def list(
        self, app_id: UUID, *, status: str | None = None, active_only: bool = False
    ) -> list[TemplateView]:
        """The app's live templates in their display order."""
        async with self.db() as s:
            q = (
                select(Template, TemplateVersion, User)
                .join(
                    TemplateVersion,
                    (TemplateVersion.template_id == Template.id)
                    & (TemplateVersion.version == Template.current_version),
                )
                .join(User, User.id == TemplateVersion.created_by)
                .where(Template.app_id == app_id, Template.deleted_at.is_(None))
                .order_by(Template.position, Template.created_at)
            )
            if active_only:
                q = q.where(Template.status == "active")
            elif status:
                q = q.where(Template.status == status)
            return [TemplateView(t, v, u) for t, v, u in await s.execute(q)]

    async def versions(self, template_id: UUID) -> list[tuple[TemplateVersion, User]]:
        async with self.db() as s:
            rows = await s.execute(
                select(TemplateVersion, User)
                .join(User, User.id == TemplateVersion.created_by)
                .where(TemplateVersion.template_id == template_id)
                .order_by(TemplateVersion.version.desc())
            )
            return [(v, u) for v, u in rows]

    # ---- writes -------------------------------------------------------------------------------
    async def create(
        self, actor: User, app_id: UUID, body: TemplateCreate, *, status: str = "draft"
    ) -> tuple[TemplateView, list[str]]:
        warnings = await self.check(body, app_id)
        tid = uuid.uuid4()
        async with self.db.begin() as s:
            taken = await s.scalar(
                select(Template.id).where(
                    Template.app_id == app_id, Template.slug == body.slug, Template.deleted_at.is_(None)
                )
            )
            if taken:
                raise ConflictError("this app already has a template with this slug", "slug")
            # a deleted template may still hold the slug: move it out of the way
            await s.execute(
                update(Template)
                .where(Template.app_id == app_id, Template.slug == body.slug)
                .values(
                    slug=func.left(Template.slug, 40)
                    + "-deleted-"
                    + func.left(func.md5(func.cast(Template.id, String)), 8)
                )
            )
            position = await s.scalar(
                select(func.coalesce(func.max(Template.position), -1) + 1).where(Template.app_id == app_id)
            )
            s.add(
                Template(
                    id=tid,
                    app_id=app_id,
                    position=position,
                    slug=body.slug,
                    title=body.title.strip(),
                    description=body.description,
                    status=status,
                    current_version=1,
                    credit_cost=1 if body.credit_cost is None else body.credit_cost,
                    created_by=actor.id,
                )
            )
            await s.flush()
            s.add(_version_row(tid, 1, body, actor))
            s.add(TemplateEvent(template_id=tid, user_id=actor.id, action="create", to_status=status))
        return await self.get(app_id, str(tid)), warnings

    async def _write_version(
        self,
        actor: User,
        app_id: UUID,
        template_id: UUID,
        f: TemplateFields,
        base_version: int,
        action: str,
        credit_cost: int | None = None,
    ) -> TemplateView:
        async with self.db.begin() as s:
            t = await s.get(Template, template_id, with_for_update=True)
            if t is None or t.app_id != app_id or t.deleted_at is not None:
                raise NotFoundError("template not found")
            if base_version != t.current_version:
                last = await s.get(TemplateVersion, (t.id, t.current_version))
                who = await s.get(User, last.created_by)
                raise ConflictError(
                    f"version {t.current_version} was saved by {who.name if who else 'someone'} after you "
                    f"opened version {base_version}",
                    details=[{"current_version": t.current_version, "saved_by": who.name if who else None}],
                ) from None
            t.current_version += 1
            t.title = f.title.strip()
            t.description = f.description
            if credit_cost is not None:
                t.credit_cost = credit_cost
            t.updated_at = func.now()
            s.add(_version_row(t.id, t.current_version, f, actor))
            s.add(TemplateEvent(template_id=t.id, user_id=actor.id, action=action))
        return await self.get(app_id, str(template_id))

    async def update(
        self, actor: User, app_id: UUID, template_id: UUID, body: TemplateUpdate
    ) -> tuple[TemplateView, list[str]]:
        warnings = await self.check(body, app_id)
        view = await self._write_version(
            actor, app_id, template_id, body, body.base_version, "update", body.credit_cost
        )
        return view, warnings

    def _fields_of(self, v: TemplateVersion, note: str | None) -> TemplateFields:
        return TemplateFields(
            **{
                k: getattr(v, k)
                for k in VERSION_FIELDS
                if k not in ("reference_uploads", "cover_upload", "note")
            },
            reference_uploads=[str(u) for u in v.reference_uploads],
            cover_upload=str(v.cover_upload) if v.cover_upload else None,
            note=note,
        )

    async def restore(
        self, actor: User, app_id: UUID, template_id: UUID, version: int
    ) -> tuple[TemplateView, list[str]]:
        old = await self.get(app_id, str(template_id), version)
        fields = self._fields_of(old.version, f"restored from version {version}")
        warnings = await self.check(fields, app_id)
        view = await self._write_version(
            actor, app_id, template_id, fields, old.template.current_version, "restore"
        )
        return view, warnings

    async def set_status(self, actor: User, app_id: UUID, template_id: UUID, status: str) -> TemplateView:
        if status not in ("draft", "active"):
            raise ValidationFailed("status must be draft or active", "status")
        async with self.db.begin() as s:
            t = await s.get(Template, template_id, with_for_update=True)
            if t is None or t.app_id != app_id or t.deleted_at is not None:
                raise NotFoundError("template not found")
            if t.status != status:
                s.add(
                    TemplateEvent(
                        template_id=t.id,
                        user_id=actor.id,
                        action="status",
                        from_status=t.status,
                        to_status=status,
                    )
                )
                t.status = status
                t.updated_at = func.now()
        return await self.get(app_id, str(template_id))

    async def delete(self, actor: User, app_id: UUID, template_id: UUID) -> None:
        """Soft delete: gone from the app, its catalog and runs; past jobs keep its name."""
        async with self.db.begin() as s:
            t = await s.get(Template, template_id, with_for_update=True)
            if t is None or t.app_id != app_id or t.deleted_at is not None:
                raise NotFoundError("template not found")
            t.deleted_at = func.now()
            t.updated_at = func.now()
            s.add(TemplateEvent(template_id=t.id, user_id=actor.id, action="delete", from_status=t.status))

    async def reorder(self, app_id: UUID, template_ids: list[UUID]) -> None:
        """Set the display order; the list must name every live template of the app once."""
        async with self.db.begin() as s:
            live = set(
                await s.scalars(
                    select(Template.id).where(Template.app_id == app_id, Template.deleted_at.is_(None))
                )
            )
            if len(template_ids) != len(set(template_ids)) or set(template_ids) != live:
                raise ValidationFailed("list every template of the app exactly once", "template_ids")
            for i, tid in enumerate(template_ids):
                await s.execute(update(Template).where(Template.id == tid).values(position=i))

    async def copy(
        self, actor: User, app_id: UUID, template_id: UUID, target_app_id: UUID, slug: str | None
    ) -> tuple[TemplateView, list[str]]:
        """Copy the current version into another app as a new draft (version 1). Its cover and
        reference images get upload rows in the target app that point at the same (immutable)
        files, so nothing is duplicated on disk."""
        src = await self.get(app_id, str(template_id))
        fields = self._fields_of(src.version, f"copied from {src.template.slug} v{src.version.version}")
        mapping: dict[str, str] = {}
        wanted = [u for u in [fields.cover_upload, *fields.reference_uploads] if u]
        if wanted:
            async with self.db.begin() as s:
                rows = await s.scalars(select(Upload).where(Upload.id.in_([UUID(u) for u in wanted])))
                for row in rows:
                    new_id = uuid.uuid4()
                    s.add(
                        Upload(
                            id=new_id,
                            path=row.path,
                            mime_type=row.mime_type,
                            size_bytes=row.size_bytes,
                            width=row.width,
                            height=row.height,
                            sha256=row.sha256,
                            app_id=target_app_id,
                            created_by=actor.id,
                        )
                    )
                    mapping[str(row.id)] = str(new_id)
        body = TemplateCreate(
            **fields.model_dump(exclude={"cover_upload", "reference_uploads"}),
            cover_upload=mapping.get(fields.cover_upload) if fields.cover_upload else None,
            reference_uploads=[mapping[u] for u in fields.reference_uploads if u in mapping],
            slug=slug or src.template.slug,
            credit_cost=src.template.credit_cost,
        )
        return await self.create(actor, target_app_id, body)

    async def add_upload(self, actor: User, app_id: UUID, file: UploadFile) -> Upload:
        clean = await self._clean(file, "file")
        uid = uuid.uuid4()
        path = await self.store.put_upload(str(uid), clean.data, clean.ext)
        row = Upload(
            id=uid,
            path=path,
            mime_type=clean.mime_type,
            size_bytes=len(clean.data),
            width=clean.width,
            height=clean.height,
            sha256=clean.sha256,
            app_id=app_id,
            created_by=actor.id,
        )
        async with self.db.begin() as s:
            s.add(row)
        return row

    async def get_upload(self, upload_id: UUID) -> Upload | None:
        async with self.db() as s:
            return await s.get(Upload, upload_id)

    # ---- template call -> job ------------------------------------------------------------------------
    async def _clean(self, file: UploadFile, field: str):
        from creative.errors import PayloadTooLarge

        try:
            data = await read_upload(file, self.settings.input_image_max_bytes)
            return normalize_image(
                data,
                max_pixels=self.settings.input_image_max_pixels,
                max_side=self.settings.input_image_max_side,
            )
        except ImageTooLarge as e:
            raise PayloadTooLarge(f"{field}: {e}", field) from e
        except InvalidImage as e:
            raise ValidationFailed(f"{field}: {e}", field, [{"field": field, "message": str(e)}]) from e

    async def build_job(
        self,
        actor: User | None,
        *,
        app_id: UUID,
        can_edit: bool,
        ref: str,
        files: dict[str, UploadFile],
        variables: dict | None,
        model: str | None,
        webhook_url: str | None,
        version: int | None,
        device_id: str | None = None,
        app_user: AppUser | None = None,
    ) -> Job:
        """A template call becomes an ordinary job of the app. `actor` is None for calls made with
        an app key. Only editors may run drafts or a specific version. A signed-in `app_user` pays
        the template's credit cost (checked here, charged atomically with the job's insert). An
        app-key call without a user may only run free templates, even when the app doesn't require
        sign-in: the key ships inside the app and can be extracted. Console runs are never charged."""
        if version is not None and not can_edit:
            raise ForbiddenError("only editors can run a specific version")
        view = await self.get(app_id, ref, version, active_only=not can_edit)
        t, v = view.template, view.version
        if actor is None and app_user is None and t.credit_cost > 0:
            raise SignInRequired(f"sign in to use this template (it costs {t.credit_cost} credits)")
        cost = t.credit_cost if app_user else 0
        if cost and app_user.credits < cost:
            raise InsufficientCredits(
                f"this needs {cost} credits and the account has {app_user.credits}",
                details=[{"credits": app_user.credits, "required": cost}],
            )

        slots = {s["name"]: s for s in v.inputs}
        errors = [{"field": n, "message": "unknown input slot"} for n in files if n not in slots]
        errors += [
            {"field": n, "message": "this image is required"}
            for n, s in slots.items()
            if s.get("required", True) and n not in files
        ]
        if errors:
            raise ValidationFailed("missing or unknown images", details=errors)

        chosen = model or v.model
        if chosen != v.model and chosen not in v.allowed_models:
            raise ValidationFailed("this model is not allowed for the template", "model")

        values = resolve_values([Variable(**x) for x in v.variables], variables)
        prompt = render(v.prompt, values)
        negative = render(v.negative_prompt, values)

        provider = self.registry.get(v.provider)
        if provider is None:
            raise UnavailableError(f"provider {v.provider} is not configured on this server")

        cleaned = {name: await self._clean(f, name) for name, f in files.items()}
        refs: list[Upload] = []
        if v.reference_uploads:
            async with self.db() as s:
                refs = list(await s.scalars(select(Upload).where(Upload.id.in_(v.reference_uploads))))

        params = v.params
        aspect = None if params.get("aspect_ratio", "auto") == "auto" else params["aspect_ratio"]
        probe = GenerationRequest(
            job_id="probe",
            prompt=prompt,
            media_type=MediaType(v.media_type),
            model=chosen,
            aspect_ratio=aspect,
            n=params.get("n", 1),
            duration_seconds=params.get("duration_seconds"),
            negative_prompt=negative,
            seed=params.get("seed"),
            input_images=[
                InputImage(self.store.temp_dir(), c.mime_type, c.width, c.height) for c in cleaned.values()
            ]
            + [InputImage(self.store.temp_dir(), r.mime_type, r.width, r.height, "reference") for r in refs],
        )
        try:
            provider.validate(probe)
        except UnsupportedRequestError as e:
            raise ValidationFailed(e.message, e.field) from e

        job_id = uuid.uuid4()
        inputs: list[JobInput] = []
        try:
            for name, c in cleaned.items():
                path = await self.store.put_input(str(job_id), name, c.data, c.ext)
                inputs.append(
                    JobInput(
                        id=uuid.uuid4(),
                        job_id=job_id,
                        slot=name,
                        role="input",
                        path=path,
                        mime_type=c.mime_type,
                        size_bytes=len(c.data),
                        width=c.width,
                        height=c.height,
                        sha256=c.sha256,
                    )
                )
            for i, r in enumerate(refs):
                inputs.append(
                    JobInput(
                        id=uuid.uuid4(),
                        job_id=job_id,
                        slot=f"_reference_{i}",
                        role="reference",
                        path=r.path,
                        mime_type=r.mime_type,
                        size_bytes=r.size_bytes,
                        width=r.width,
                        height=r.height,
                        sha256=r.sha256,
                    )
                )
            job = Job(
                id=job_id,
                status="queued",
                media_type=v.media_type,
                provider=v.provider,
                model=chosen,
                request={
                    "prompt": prompt,
                    "negative_prompt": negative,
                    "aspect_ratio": aspect,
                    "n": params.get("n", 1),
                    "duration_seconds": params.get("duration_seconds"),
                    "seed": params.get("seed"),
                    "variables": values,
                },
                webhook_url=webhook_url,
                webhook_status="pending" if webhook_url else None,
                max_attempts=self.settings.job_max_attempts,
                created_by=actor.id if actor else None,
                template_id=t.id,
                template_version=v.version,
                app_id=app_id,
                device_id=device_id,
                app_user_id=app_user.id if app_user else None,
                credits_charged=cost,
            )
            await self.jobs.create(job, inputs)
        except Exception:
            await self.store.delete_inputs(str(job_id))
            raise
        return job
