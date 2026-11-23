from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from creative.api.schemas import HealthResponse, ProviderInfo
from creative.deps import AppState, get_state, public, signed_in

router = APIRouter(tags=["meta"])


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


@router.get("/v1/providers", response_model=list[ProviderInfo], dependencies=[Depends(signed_in)])
async def providers(state: AppState = Depends(get_state)):
    out = []
    for p in state.registry.list():
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
