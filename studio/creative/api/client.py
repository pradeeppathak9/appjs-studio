"""The API for an app's clients (e.g. the Android app), authenticated with `X-App-Key`.

When the app has `require_login` on, these calls also need the end user's session
(`Authorization: Bearer cas_...`, see client_auth.py). A signed-in user pays each template's
`credit_cost` and sees only their own jobs."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from creative.api.assets import serve_file
from creative.api.schemas import AppCatalog, AppRunResponse, JobResponse, TemplatePublic
from creative.api.templates import TEMPLATE_FORM_SCHEMA, catalog, parse_template_form, public_of, serve_cover
from creative.apps.service import AppPrincipal
from creative.deps import AppState, app_key, app_user_if_required, get_state
from creative.errors import NotFoundError
from creative.jobs.repository import JobFilter

router = APIRouter(prefix="/v1/app", tags=["app clients"])

APP_FORM_FIELDS = {"variables", "model"}  # clients don't set webhooks or pick versions


@router.get("/templates", response_model=AppCatalog)
async def app_templates(
    a: AppPrincipal = Depends(app_user_if_required), state: AppState = Depends(get_state)
):
    """The app's active templates, in the order set in its dashboard."""
    return await catalog(state, a.app)


@router.get("/templates/{ref}", response_model=TemplatePublic)
async def app_template(
    ref: str, a: AppPrincipal = Depends(app_user_if_required), state: AppState = Depends(get_state)
):
    return public_of(await state.templates.get(a.app.id, ref, active_only=True), "/v1/app")


@router.get("/templates/{ref}/cover", response_class=FileResponse)
async def app_template_cover(
    ref: str, a: AppPrincipal = Depends(app_key), state: AppState = Depends(get_state)
):
    return await serve_cover(state, await state.templates.get(a.app.id, ref, active_only=True))


@router.post(
    "/templates/{ref}/generations",
    response_model=AppRunResponse,
    status_code=202,
    openapi_extra=TEMPLATE_FORM_SCHEMA,
)
async def app_run_template(
    ref: str,
    request: Request,
    a: AppPrincipal = Depends(app_user_if_required),
    state: AppState = Depends(get_state),
):
    """Run a template with the user's photo. A signed-in user pays its `credit_cost` (402
    `insufficient_credits` when short; refunded if the job fails) and gets the new balance as
    `credits`. Without a signed-in user only free templates run (401 otherwise)."""
    await state.apps.check_limits(a.app, a.device_id)
    form, parsed = await parse_template_form(request, state, APP_FORM_FIELDS)
    try:
        job = await state.templates.build_job(
            None,
            app_id=a.app.id,
            can_edit=False,
            ref=ref,
            device_id=a.device_id,
            app_user=a.user,
            **parsed,
        )
    finally:
        await form.close()
    job = await state.repo.get(job.id)
    out = (await state.generations.to_responses([job], None, "/v1/app"))[0]
    # read after the charge committed, so it is the balance the ledger holds now
    credits = (await state.endusers.get(a.app.id, a.user.id)).credits if a.user else None
    return {**out, "credits": credits}


async def _client_job(state: AppState, a: AppPrincipal, job_id: UUID):
    job = await state.repo.get(job_id)
    # Visible to the app's clients only for jobs they made (no console tests). A signed-in user's
    # job only to that user; otherwise, when a device id was sent, only to that device.
    if job is None or job.app_id != a.app.id or job.created_by is not None:
        raise NotFoundError("job not found")
    if job.app_user_id is not None:
        if a.user is None or a.user.id != job.app_user_id:
            raise NotFoundError("job not found")
    elif a.user is not None or (job.device_id and a.device_id != job.device_id):
        raise NotFoundError("job not found")
    return job


@router.get("/generations", response_model=list[JobResponse])
async def app_jobs(
    limit: int = 20, a: AppPrincipal = Depends(app_user_if_required), state: AppState = Depends(get_state)
):
    """Recent jobs, newest first: the signed-in user's, or else this device's (needs X-Device-Id)."""
    limit = min(max(limit, 1), 100)
    if a.user is not None:
        jobs = await state.repo.list(JobFilter(app_id=a.app.id, app_user_id=a.user.id, limit=limit))
    elif a.device_id:
        jobs = await state.repo.list(JobFilter(app_id=a.app.id, device_id=a.device_id, limit=limit))
        jobs = [j for j in jobs if j.app_user_id is None]
    else:
        return []
    return await state.generations.to_responses([j for j in jobs if j.created_by is None], None, "/v1/app")


@router.get("/generations/{job_id}", response_model=JobResponse)
async def app_job(
    job_id: UUID, a: AppPrincipal = Depends(app_user_if_required), state: AppState = Depends(get_state)
):
    job = await _client_job(state, a, job_id)
    return (await state.generations.to_responses([job], None, "/v1/app"))[0]


@router.get("/assets/{asset_id}", response_class=FileResponse)
async def app_asset(
    asset_id: UUID, a: AppPrincipal = Depends(app_user_if_required), state: AppState = Depends(get_state)
):
    found = await state.repo.get_asset(asset_id)
    if not found:
        raise NotFoundError("asset not found")
    asset, job = found
    await _client_job(state, a, job.id)
    return serve_file(
        state, asset.path, asset.mime_type, f"{job.id}-{asset.idx}.{asset.path.rsplit('.', 1)[-1]}"
    )


@router.get("/inputs/{input_id}", response_class=FileResponse)
async def app_input(
    input_id: UUID, a: AppPrincipal = Depends(app_user_if_required), state: AppState = Depends(get_state)
):
    found = await state.repo.get_input(input_id)
    if not found or found[0].role != "input":
        raise NotFoundError("input not found")
    item, job = found
    await _client_job(state, a, job.id)
    return serve_file(
        state, item.path, item.mime_type, f"{job.id}-{item.slot}.{item.path.rsplit('.', 1)[-1]}"
    )
