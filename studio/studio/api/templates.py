"""The app dashboard: everything under /v1/apps/{app_id}. Testers run active templates and see
their own jobs; editors also manage the app's templates and see all its jobs."""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile as StarletteUploadFile

from studio.api.assets import serve_file
from studio.api.schemas import (
    AppCatalog,
    AppInfo,
    GenerationCreate,
    JobList,
    JobResponse,
    MyApp,
    TemplateCopyIn,
    TemplateFull,
    TemplateOrderIn,
    TemplatePublic,
    TemplateSaved,
    TemplateStatusIn,
    TemplateVersionOut,
    UploadOut,
    UserRef,
)
from studio.auth.service import AppRole, Principal
from studio.deps import AppContext, AppState, Forbidden, editor, get_state, signed_in, tester
from studio.errors import NotFoundError, ValidationFailed
from studio.jobs.repository import JobFilter
from studio.templates.models import TemplateCreate, TemplateUpdate
from studio.templates.service import TemplateView

apps_router = APIRouter(prefix="/v1/apps", tags=["apps"])
router = APIRouter(prefix="/v1/apps/{app_id}", tags=["app dashboard"])
manage = APIRouter(prefix="/v1/apps/{app_id}/manage/templates", tags=["app dashboard"])

TEMPLATE_FORM_SCHEMA = {
    "requestBody": {
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "description": "One file field per input slot, named after the slot.",
                    "properties": {
                        "variables": {"type": "string", "description": "JSON object"},
                        "model": {"type": "string"},
                        "webhook_url": {"type": "string"},
                        "version": {"type": "integer", "description": "editors only"},
                    },
                    "additionalProperties": {"type": "string", "format": "binary"},
                }
            }
        },
        "required": True,
    }
}

FORM_FIELDS = {"variables", "model", "webhook_url", "version"}


async def parse_template_form(request: Request, state: AppState, allowed=FORM_FIELDS):
    """Split a template-call form into image files (one per slot) and the known text fields.
    Returns the open form (close it when done) and keyword arguments for `build_job`."""
    form = await request.form(
        max_files=16, max_fields=32, max_part_size=state.settings.input_image_max_bytes + 1024 * 1024
    )
    files: dict[str, UploadFile] = {}
    fields: dict[str, str] = {}
    errors = []
    for key, value in form.multi_items():
        if isinstance(value, StarletteUploadFile):
            if key in files:
                errors.append({"field": key, "message": "one file per slot"})
            files[key] = value
        elif key in allowed:
            fields[key] = value
        else:
            errors.append({"field": key, "message": "unknown form field"})
    variables = None
    if fields.get("variables"):
        try:
            variables = json.loads(fields["variables"])
            if not isinstance(variables, dict):
                raise ValueError
        except ValueError:
            errors.append({"field": "variables", "message": "must be a JSON object"})
    version = None
    if fields.get("version"):
        try:
            version = int(fields["version"])
        except ValueError:
            errors.append({"field": "version", "message": "must be an integer"})
    if errors:
        await form.close()
        raise ValidationFailed("the form is invalid", details=errors)
    return form, {
        "files": files,
        "variables": variables,
        "model": fields.get("model") or None,
        "webhook_url": fields.get("webhook_url") or None,
        "version": version,
    }


def cover_url(view: TemplateView, url_base: str) -> str | None:
    t, v = view.template, view.version
    return f"{url_base}/templates/{t.slug}/cover?v={v.version}" if v.cover_upload else None


def public_of(view: TemplateView, url_base: str) -> TemplatePublic:
    t, v = view.template, view.version
    return TemplatePublic(
        id=t.id,
        slug=t.slug,
        title=t.title,
        description=t.description,
        media_type=v.media_type,
        version=v.version,
        inputs=v.inputs,
        variables=v.variables,
        model=v.model,
        allowed_models=v.allowed_models,
        has_reference_images=bool(v.reference_uploads),
        cover_url=cover_url(view, url_base),
        credit_cost=t.credit_cost,
    )


def version_of(v, user) -> TemplateVersionOut:
    return TemplateVersionOut(
        version=v.version,
        title=v.title,
        description=v.description,
        media_type=v.media_type,
        provider=v.provider,
        model=v.model,
        allowed_models=v.allowed_models,
        prompt=v.prompt,
        negative_prompt=v.negative_prompt,
        params=v.params,
        inputs=v.inputs,
        variables=v.variables,
        reference_uploads=v.reference_uploads,
        cover_upload=v.cover_upload,
        note=v.note,
        created_by=UserRef(id=user.id, name=user.name),
        created_at=v.created_at,
    )


async def full_of(state: AppState, view: TemplateView, with_versions: bool = False) -> TemplateFull:
    t = view.template
    versions = None
    if with_versions:
        versions = [version_of(v, u) for v, u in await state.templates.versions(t.id)]
    return TemplateFull(
        id=t.id,
        app_id=t.app_id,
        slug=t.slug,
        title=t.title,
        description=t.description,
        status=t.status,
        position=t.position,
        current_version=t.current_version,
        credit_cost=t.credit_cost,
        cover_url=cover_url(view, f"/v1/apps/{t.app_id}"),
        created_at=t.created_at,
        updated_at=t.updated_at,
        current=version_of(view.version, view.editor),
        versions=versions,
    )


async def serve_cover(state: AppState, view: TemplateView):
    if not view.version.cover_upload:
        raise NotFoundError("this template has no cover image")
    row = await state.templates.get_upload(view.version.cover_upload)
    if row is None:
        raise NotFoundError("cover image is gone")
    return serve_file(state, row.path, row.mime_type, f"{view.template.slug}.{row.path.rsplit('.', 1)[-1]}")


# ---- my apps -----------------------------------------------------------------------------------


@apps_router.get("", response_model=list[MyApp])
async def list_my_apps(p: Principal = Depends(signed_in), state: AppState = Depends(get_state)):
    """The apps the signed-in user can open (admins: all), with their role in each."""
    from studio.api.admin import app_out

    pairs = await state.apps.visible_to(p.user)
    counts = await state.apps.counts([a.id for a, _ in pairs])
    return [MyApp(**app_out(a, counts[a.id]).model_dump(), role=r.name) for a, r in pairs]


@router.get("", response_model=MyApp)
async def get_my_app(ctx: AppContext = Depends(tester), state: AppState = Depends(get_state)):
    from studio.api.admin import app_out

    counts = (await state.apps.counts([ctx.app.id]))[ctx.app.id]
    return MyApp(**app_out(ctx.app, counts).model_dump(), role=ctx.role.name)


# ---- testers and up: run active templates ------------------------------------------------------------


@router.get("/templates", response_model=list[TemplatePublic])
async def list_templates(ctx: AppContext = Depends(tester), state: AppState = Depends(get_state)):
    """Active templates, in the app's order (what testers and the app's clients see)."""
    base = f"/v1/apps/{ctx.app.id}"
    return [public_of(v, base) for v in await state.templates.list(ctx.app.id, active_only=True)]


@router.get("/templates/{ref}", response_model=TemplatePublic)
async def get_template(ref: str, ctx: AppContext = Depends(tester), state: AppState = Depends(get_state)):
    view = await state.templates.get(ctx.app.id, ref, active_only=not ctx.can_edit)
    return public_of(view, f"/v1/apps/{ctx.app.id}")


@router.get("/templates/{ref}/cover", response_class=FileResponse)
async def template_cover(ref: str, ctx: AppContext = Depends(tester), state: AppState = Depends(get_state)):
    return await serve_cover(state, await state.templates.get(ctx.app.id, ref, active_only=not ctx.can_edit))


@router.post(
    "/templates/{ref}/generations",
    response_model=JobResponse,
    status_code=202,
    openapi_extra=TEMPLATE_FORM_SCHEMA,
)
async def run_template(
    ref: str, request: Request, ctx: AppContext = Depends(tester), state: AppState = Depends(get_state)
):
    form, parsed = await parse_template_form(request, state)
    try:
        job = await state.templates.build_job(
            ctx.principal.user, app_id=ctx.app.id, can_edit=ctx.can_edit, ref=ref, **parsed
        )
    finally:
        await form.close()
    job = await state.repo.get(job.id)
    return (await state.generations.to_responses([job], ctx.role))[0]


@router.get("/generations", response_model=JobList)
async def list_app_jobs(
    status: str | None = Query(None, pattern="^(queued|running|succeeded|failed)$"),
    template: UUID | None = None,
    created_by: UUID | None = None,
    source: str | None = Query(None, pattern="^(console|app)$"),
    limit: int = Query(50, ge=1, le=200),
    ctx: AppContext = Depends(tester),
    state: AppState = Depends(get_state),
):
    """Testers: their own jobs. Editors: every job of the app; `source=app` for jobs from the
    app's clients (app key), `source=console` for jobs run here."""
    jobs = await state.generations.list_in_app(
        ctx.principal,
        ctx.role,
        JobFilter(status=status, template_id=template, created_by=created_by, app_id=ctx.app.id, limit=limit),
    )
    if source == "app":
        jobs = [j for j in jobs if j.created_by is None]
    elif source == "console":
        jobs = [j for j in jobs if j.created_by is not None]
    return JobList(items=await state.generations.to_responses(jobs, ctx.role))


# ---- editors: free prompt, catalog, uploads --------------------------------------------------------


@router.post("/generations", response_model=JobResponse, status_code=202)
async def create_generation(
    body: GenerationCreate, ctx: AppContext = Depends(editor), state: AppState = Depends(get_state)
):
    """A free-prompt test inside the app (no template)."""
    job = await state.generations.create(ctx.principal.user, ctx.app.id, body)
    job = await state.repo.get(job.id)
    return (await state.generations.to_responses([job], ctx.role))[0]


@router.get("/catalog", response_model=AppCatalog)
async def preview_catalog(ctx: AppContext = Depends(editor), state: AppState = Depends(get_state)):
    """Exactly what the app's clients receive from GET /v1/app/templates."""
    return await catalog(state, ctx.app)


async def catalog(state: AppState, app) -> AppCatalog:
    return AppCatalog(
        app=AppInfo(slug=app.slug, name=app.name, description=app.description, platform=app.platform),
        templates=[public_of(v, "/v1/app") for v in await state.templates.list(app.id, active_only=True)],
    )


@router.post("/uploads", response_model=UploadOut, status_code=201)
async def upload(
    file: UploadFile = File(...), ctx: AppContext = Depends(editor), state: AppState = Depends(get_state)
):
    """Cover and reference images for this app's templates."""
    row = await state.templates.add_upload(ctx.principal.user, ctx.app.id, file)
    return UploadOut(
        id=row.id,
        url=f"/v1/apps/{ctx.app.id}/uploads/{row.id}",
        mime_type=row.mime_type,
        width=row.width,
        height=row.height,
    )


@router.get("/uploads/{upload_id}", response_class=FileResponse)
async def get_upload(
    upload_id: UUID, ctx: AppContext = Depends(editor), state: AppState = Depends(get_state)
):
    row = await state.templates.get_upload(upload_id)
    if row is None or (row.app_id is not None and row.app_id != ctx.app.id):
        raise NotFoundError("upload not found")
    return serve_file(state, row.path, row.mime_type, f"{row.id}.{row.path.rsplit('.', 1)[-1]}")


# ---- editors: manage templates -----------------------------------------------------------------------


@manage.get("", response_model=list[TemplateFull])
async def manage_list(
    status: str | None = Query(None, pattern="^(draft|active)$"),
    ctx: AppContext = Depends(editor),
    state: AppState = Depends(get_state),
):
    return [await full_of(state, v) for v in await state.templates.list(ctx.app.id, status=status)]


@manage.post("", response_model=TemplateSaved, status_code=201)
async def manage_create(
    body: TemplateCreate, ctx: AppContext = Depends(editor), state: AppState = Depends(get_state)
):
    view, warnings = await state.templates.create(ctx.principal.user, ctx.app.id, body)
    return TemplateSaved(template=await full_of(state, view, True), warnings=warnings)


@manage.put("/order", status_code=204)
async def manage_order(
    body: TemplateOrderIn, ctx: AppContext = Depends(editor), state: AppState = Depends(get_state)
):
    """The display order (also the order the app's clients get). List every template once."""
    await state.templates.reorder(ctx.app.id, body.template_ids)
    return Response(status_code=204)


@manage.get("/{template_id}", response_model=TemplateFull)
async def manage_get(
    template_id: UUID, ctx: AppContext = Depends(editor), state: AppState = Depends(get_state)
):
    return await full_of(state, await state.templates.get(ctx.app.id, str(template_id)), True)


@manage.put("/{template_id}", response_model=TemplateSaved)
async def manage_update(
    template_id: UUID,
    body: TemplateUpdate,
    ctx: AppContext = Depends(editor),
    state: AppState = Depends(get_state),
):
    view, warnings = await state.templates.update(ctx.principal.user, ctx.app.id, template_id, body)
    return TemplateSaved(template=await full_of(state, view, True), warnings=warnings)


@manage.delete("/{template_id}", status_code=204)
async def manage_delete(
    template_id: UUID, ctx: AppContext = Depends(editor), state: AppState = Depends(get_state)
):
    """Soft delete: gone from the app and its clients; past jobs keep the template's name."""
    await state.templates.delete(ctx.principal.user, ctx.app.id, template_id)
    return Response(status_code=204)


@manage.get("/{template_id}/versions/{version}", response_model=TemplateVersionOut)
async def manage_version(
    template_id: UUID, version: int, ctx: AppContext = Depends(editor), state: AppState = Depends(get_state)
):
    view = await state.templates.get(ctx.app.id, str(template_id), version)
    return version_of(view.version, view.editor)


@manage.post("/{template_id}/versions/{version}/restore", response_model=TemplateSaved)
async def manage_restore(
    template_id: UUID, version: int, ctx: AppContext = Depends(editor), state: AppState = Depends(get_state)
):
    view, warnings = await state.templates.restore(ctx.principal.user, ctx.app.id, template_id, version)
    return TemplateSaved(template=await full_of(state, view, True), warnings=warnings)


@manage.post("/{template_id}/status", response_model=TemplateFull)
async def manage_status(
    template_id: UUID,
    body: TemplateStatusIn,
    ctx: AppContext = Depends(editor),
    state: AppState = Depends(get_state),
):
    view = await state.templates.set_status(ctx.principal.user, ctx.app.id, template_id, body.status)
    return await full_of(state, view, True)


@manage.post("/{template_id}/copy", response_model=TemplateSaved, status_code=201)
async def manage_copy(
    template_id: UUID,
    body: TemplateCopyIn,
    ctx: AppContext = Depends(editor),
    state: AppState = Depends(get_state),
):
    """Copy into another app (where you must be an editor too) as a new draft."""
    target_role = await state.apps.role_of(ctx.principal.user, body.target_app_id)
    if target_role is None:
        raise NotFoundError("target app not found", "target_app_id")
    if target_role < AppRole.editor:
        raise Forbidden("you need the editor role in the target app")
    await state.apps.get(body.target_app_id)
    view, warnings = await state.templates.copy(
        ctx.principal.user, ctx.app.id, template_id, body.target_app_id, body.slug
    )
    return TemplateSaved(template=await full_of(state, view, True), warnings=warnings)
