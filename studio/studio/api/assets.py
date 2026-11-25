from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, RedirectResponse

from studio.auth.service import AppRole, Principal
from studio.deps import AppState, get_state, signed_in
from studio.errors import NotFoundError

router = APIRouter(tags=["jobs"])


def serve_file(state: AppState, rel_path: str, mime_type: str, filename: str):
    if url := state.store.public_url(rel_path, mime_type, filename):
        # a presigned URL (or the CDN's); cache the redirect for less than the URL lives
        ttl = min(300, max(0, state.settings.s3_url_expiry_s - 60))
        return RedirectResponse(url, status_code=307, headers={"Cache-Control": f"private, max-age={ttl}"})
    path = state.store.local_path(rel_path)
    if not path.is_file():
        raise NotFoundError("file is gone")
    return FileResponse(
        path,
        media_type=mime_type,
        filename=filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/v1/assets/{asset_id}", response_class=FileResponse)
async def get_asset(asset_id: UUID, p: Principal = Depends(signed_in), state: AppState = Depends(get_state)):
    found = await state.repo.get_asset(asset_id)
    if not found:
        raise NotFoundError("asset not found")
    asset, job = found
    await state.generations.visible(p, job)
    return serve_file(
        state, asset.path, asset.mime_type, f"{job.id}-{asset.idx}.{asset.path.rsplit('.', 1)[-1]}"
    )


@router.get("/v1/inputs/{input_id}", response_class=FileResponse)
async def get_input(input_id: UUID, p: Principal = Depends(signed_in), state: AppState = Depends(get_state)):
    found = await state.repo.get_input(input_id)
    if not found:
        raise NotFoundError("input not found")
    item, job = found
    role = await state.generations.visible(p, job)
    if item.role != "input" and role < AppRole.editor:
        raise NotFoundError("input not found")
    return serve_file(
        state, item.path, item.mime_type, f"{job.id}-{item.slot}.{item.path.rsplit('.', 1)[-1]}"
    )
