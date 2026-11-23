"""A job by id, for whoever may see it (lists live under each app: /v1/apps/{app_id}/generations)."""

from uuid import UUID

from fastapi import APIRouter, Depends

from creative.api.schemas import JobResponse
from creative.auth.service import Principal
from creative.deps import AppState, get_state, signed_in

router = APIRouter(prefix="/v1/generations", tags=["jobs"])


@router.get("/{job_id}", response_model=JobResponse)
async def get_generation(
    job_id: UUID, p: Principal = Depends(signed_in), state: AppState = Depends(get_state)
):
    job, role = await state.generations.get_visible(p, job_id)
    return (await state.generations.to_responses([job], role))[0]
