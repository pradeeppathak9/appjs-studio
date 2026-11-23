from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from studio.api.schemas import (
    LoginIn,
    MeResponse,
    NameChange,
    PasswordChange,
    SetupIn,
    SetupState,
    TokenCreate,
    TokenCreated,
    TokenOut,
)
from studio.auth.service import Principal
from studio.deps import SESSION_COOKIE, AppState, get_state, public, signed_in_pending_ok

router = APIRouter(prefix="/v1/auth", tags=["auth"])


def me_of(p_user) -> MeResponse:
    return MeResponse(
        id=p_user.id,
        email=p_user.email,
        name=p_user.name,
        role=p_user.role,
        must_change_password=p_user.must_change_password,
    )


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def set_session_cookie(response: Response, state: AppState, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        secure=state.settings.cookie_secure,
        path="/",
        max_age=int(state.settings.session_max_age_hours * 3600),
    )


@router.get("/setup", response_model=SetupState, dependencies=[Depends(public())])
async def setup_state(state: AppState = Depends(get_state)):
    return SetupState(needed=await state.auth.setup_needed())


@router.post("/setup", response_model=MeResponse, status_code=201, dependencies=[Depends(public())])
async def setup(body: SetupIn, request: Request, response: Response, state: AppState = Depends(get_state)):
    user = await state.auth.setup(body.setup_token, body.email, body.name, body.password)
    token = await state.auth.new_session(user.id, client_ip(request), request.headers.get("user-agent"))
    set_session_cookie(response, state, token)
    return me_of(user)


@router.post("/login", response_model=MeResponse, dependencies=[Depends(public())])
async def login(body: LoginIn, request: Request, response: Response, state: AppState = Depends(get_state)):
    user, token = await state.auth.login(
        body.email, body.password, client_ip(request), request.headers.get("user-agent")
    )
    set_session_cookie(response, state, token)
    return me_of(user)


@router.post("/logout", status_code=204, dependencies=[Depends(public())])
async def logout(request: Request, state: AppState = Depends(get_state)):
    if token := request.cookies.get(SESSION_COOKIE):
        await state.auth.end_session(token)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.get("/me", response_model=MeResponse)
async def me(p: Principal = Depends(signed_in_pending_ok)):
    return me_of(p.user)


@router.patch("/me", response_model=MeResponse)
async def rename(
    body: NameChange, p: Principal = Depends(signed_in_pending_ok), state: AppState = Depends(get_state)
):
    await state.auth.rename(p.user.id, body.name)
    return me_of(await state.auth.get_user(p.user.id))


@router.post("/password", status_code=204)
async def change_password(
    body: PasswordChange, p: Principal = Depends(signed_in_pending_ok), state: AppState = Depends(get_state)
):
    await state.auth.change_password(p, body.current_password, body.new_password)
    return Response(status_code=204)


@router.get("/tokens", response_model=list[TokenOut])
async def list_tokens(p: Principal = Depends(signed_in_pending_ok), state: AppState = Depends(get_state)):
    return [TokenOut.model_validate(t, from_attributes=True) for t in await state.auth.list_tokens(p.user.id)]


@router.post("/tokens", response_model=TokenCreated, status_code=201)
async def create_token(
    body: TokenCreate, p: Principal = Depends(signed_in_pending_ok), state: AppState = Depends(get_state)
):
    tok, raw = await state.auth.create_token(p.user.id, body.name)
    return TokenCreated(**TokenOut.model_validate(tok, from_attributes=True).model_dump(), token=raw)


@router.delete("/tokens/{token_id}", status_code=204)
async def revoke_token(
    token_id: UUID, p: Principal = Depends(signed_in_pending_ok), state: AppState = Depends(get_state)
):
    await state.auth.revoke_token(p.user.id, token_id)
    return Response(status_code=204)
