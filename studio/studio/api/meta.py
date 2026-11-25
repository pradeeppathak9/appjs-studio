from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from studio.api.schemas import HealthResponse, ProviderInfo
from studio.auth.service import Principal
from studio.deps import AppState, get_state, public, signed_in
from studio.errors import NotFoundError
from studio.providers.pricing import PriceList, load_prices
from studio.providers.registry import ORDER

router = APIRouter(tags=["meta"])


@router.get("/v1/model-prices", response_model=PriceList, dependencies=[Depends(signed_in)])
async def model_prices():
    """What each model costs per image (or per second of video), for estimating a template's cost per
    run. List prices from `studio/providers/prices.yaml`; models without an entry have no known price."""
    return load_prices()


@router.get("/healthz", response_model=HealthResponse, dependencies=[Depends(public())])
async def healthz(state: AppState = Depends(get_state)):
    try:
        async with state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse({"status": "degraded", "db": "down", "workers": [], "jobs": {}}, status_code=503)
    workers = await state.queue.live_workers(state.settings.stale_job_after_s)
    status = "ok" if any(w["fresh"] for w in workers) else "degraded"
    return HealthResponse(status=status, db="ok", workers=workers, jobs=await state.repo.counts())


@router.get("/v1/providers", response_model=list[ProviderInfo])
async def providers(
    app_id: UUID | None = Query(
        None, description="also list providers this app has its own API key for (members of the app)"
    ),
    who: Principal = Depends(signed_in),
    state: AppState = Depends(get_state),
):
    """The providers jobs can run on: the server's, plus, with `app_id`, those the app brings a key for."""
    if app_id is None:
        available = state.registry.list()
    else:
        if await state.apps.role_of(who.user, app_id) is None:
            raise NotFoundError("app not found")
        by_name = await state.providers.all(app_id) if state.providers else dict(state.registry.providers)
        available = [by_name[n] for n in ORDER if n in by_name]
    out = []
    for p in available:
        c = p.capabilities
        out.append(
            ProviderInfo(
                name=c.name,
                image=c.image,
                video=c.video,
                default_image_model=c.default_image_model,
                default_video_model=c.default_video_model,
                known_image_models=list(c.known_image_models),
                known_video_models=list(c.known_video_models),
                max_images=c.max_images,
                image_aspect_ratios=list(c.image_aspect_ratios),
                video_aspect_ratios=list(c.video_aspect_ratios),
                video_durations=list(c.video_durations),
                supports_negative_prompt=c.supports_negative_prompt,
                supports_seed=c.supports_seed,
                image_input=c.image_input,
                image_input_models=list(c.image_input_models),
                max_input_images=c.max_input_images,
            )
        )
    return out
