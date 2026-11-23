"""Admin dashboard: users, apps, who is in which app (and as what), app keys."""

from uuid import UUID

from fastapi import APIRouter, Depends, Response

from creative.api.schemas import (
    AppDetail,
    AppKeyCreate,
    AppKeyCreated,
    AppKeyOut,
    AppOut,
    MemberIn,
    MemberOut,
    Membership,
    TemporaryPassword,
    TokenOut,
    UserCreate,
    UserCreated,
    UserOut,
    UserUpdate,
)
from creative.apps.service import AppCreate, AppFields, AppPatch, Counts
from creative.auth.service import Principal
from creative.deps import AppState, admin, get_state

router = APIRouter(prefix="/v1/admin", tags=["admin"], dependencies=[Depends(admin)])


def user_out(u, tokens: int = 0) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        name=u.name,
        role=u.role,
        is_active=u.is_active,
        must_change_password=u.must_change_password,
        created_at=u.created_at,
        last_login_at=u.last_login_at,
        active_tokens=tokens,
    )


def app_out(app, counts: Counts | None = None) -> AppOut:
    c = counts or Counts()
    return AppOut(
        id=app.id,
        slug=app.slug,
        name=app.name,
        description=app.description,
        platform=app.platform,
        status=app.status,
        daily_job_limit=app.daily_job_limit,
        device_hourly_limit=app.device_hourly_limit,
        auth_google_enabled=app.auth_google_enabled,
        auth_phone_enabled=app.auth_phone_enabled,
        google_client_ids=list(app.google_client_ids or []),
        phone_provider=app.phone_provider,
        msg91_template_id=app.msg91_template_id,
        msg91_otp_var=app.msg91_otp_var,
        msg91_auth_key_set=bool(app.msg91_auth_key_enc),
        firebase_project_id=app.firebase_project_id,
        signup_credits=app.signup_credits,
        require_login=app.require_login,
        payment_provider=app.payment_provider,
        payment_mode=app.payment_mode,
        razorpay_key_id=app.razorpay_key_id,
        phonepe_merchant_id=app.phonepe_merchant_id,
        created_at=app.created_at,
        updated_at=app.updated_at,
        template_count=c.templates,
        active_template_count=c.active_templates,
        active_key_count=c.keys,
        member_count=c.members,
    )


async def app_detail(state: AppState, app_id: UUID) -> AppDetail:
    app = await state.apps.get(app_id)
    counts = (await state.apps.counts([app_id]))[app_id]
    out = app_out(app, counts).model_dump() | {"secrets_key_set": state.apps.box.available}
    return AppDetail(**out, usage=await state.apps.usage(app_id))


# ---- users -------------------------------------------------------------------------------------------


@router.get("/users", response_model=list[UserOut])
async def list_users(state: AppState = Depends(get_state)):
    return [user_out(u, n) for u, n in await state.auth.list_users()]


@router.post("/users", response_model=UserCreated, status_code=201)
async def create_user(body: UserCreate, p: Principal = Depends(admin), state: AppState = Depends(get_state)):
    user, password = await state.auth.create_user(p.user, body.email, body.name, body.role)
    return UserCreated(user=user_out(user), temporary_password=password)


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: UUID, body: UserUpdate, p: Principal = Depends(admin), state: AppState = Depends(get_state)
):
    user = await state.auth.update_user(
        p.user, user_id, name=body.name, role=body.role, is_active=body.is_active
    )
    return user_out(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: UUID, p: Principal = Depends(admin), state: AppState = Depends(get_state)):
    """Delete a user: sign-in and tokens stop at once, the email is free again, they leave every app,
    and their name stays on the jobs and templates they made."""
    await state.auth.delete_user(p.user, user_id)
    return Response(status_code=204)


@router.post("/users/{user_id}/reset-password", response_model=TemporaryPassword)
async def reset_password(user_id: UUID, state: AppState = Depends(get_state)):
    return TemporaryPassword(temporary_password=await state.auth.reset_password(user_id))


@router.get("/users/{user_id}/tokens", response_model=list[TokenOut])
async def user_tokens(user_id: UUID, state: AppState = Depends(get_state)):
    await state.auth.get_user(user_id)
    return [TokenOut.model_validate(t, from_attributes=True) for t in await state.auth.list_tokens(user_id)]


@router.delete("/users/{user_id}/tokens/{token_id}", status_code=204)
async def revoke_user_token(user_id: UUID, token_id: UUID, state: AppState = Depends(get_state)):
    await state.auth.revoke_token(user_id, token_id)
    return Response(status_code=204)


@router.get("/users/{user_id}/apps", response_model=list[Membership])
async def user_apps(user_id: UUID, state: AppState = Depends(get_state)):
    await state.auth.get_user(user_id)
    return [
        Membership(app_id=a.id, app_slug=a.slug, app_name=a.name, role=r)
        for a, r in await state.apps.memberships(user_id)
    ]


# ---- apps --------------------------------------------------------------------------------------------


@router.get("/apps", response_model=list[AppOut])
async def list_apps(state: AppState = Depends(get_state)):
    apps = await state.apps.list_all()
    counts = await state.apps.counts([a.id for a in apps])
    return [app_out(a, counts[a.id]) for a in apps]


@router.post("/apps", response_model=AppDetail, status_code=201)
async def create_app(body: AppCreate, p: Principal = Depends(admin), state: AppState = Depends(get_state)):
    app = await state.apps.create(p.user, body)
    return await app_detail(state, app.id)


@router.get("/apps/{app_id}", response_model=AppDetail)
async def get_app(app_id: UUID, state: AppState = Depends(get_state)):
    return await app_detail(state, app_id)


@router.put("/apps/{app_id}", response_model=AppDetail)
async def update_app(app_id: UUID, body: AppFields, state: AppState = Depends(get_state)):
    await state.apps.update(app_id, body)
    return await app_detail(state, app_id)


@router.patch("/apps/{app_id}", response_model=AppDetail)
async def patch_app(app_id: UUID, body: AppPatch, state: AppState = Depends(get_state)):
    """Change only the fields sent: the app settings page saves each section on its own."""
    await state.apps.update(app_id, body)
    return await app_detail(state, app_id)


@router.delete("/apps/{app_id}", status_code=204)
async def delete_app(app_id: UUID, state: AppState = Depends(get_state)):
    """Delete an app: its keys stop working, its templates and members go; past jobs keep its name."""
    await state.apps.delete(app_id)
    return Response(status_code=204)


@router.get("/apps/{app_id}/members", response_model=list[MemberOut])
async def list_members(app_id: UUID, state: AppState = Depends(get_state)):
    await state.apps.get(app_id)
    return [
        MemberOut(user_id=u.id, name=u.name, email=u.email, role=r, is_active=u.is_active)
        for u, r in await state.apps.members(app_id)
    ]


@router.put("/apps/{app_id}/members/{user_id}", status_code=204)
async def set_member(app_id: UUID, user_id: UUID, body: MemberIn, state: AppState = Depends(get_state)):
    """Add a user to the app, or change their role in it."""
    await state.apps.set_member(app_id, user_id, body.role)
    return Response(status_code=204)


@router.delete("/apps/{app_id}/members/{user_id}", status_code=204)
async def remove_member(app_id: UUID, user_id: UUID, state: AppState = Depends(get_state)):
    await state.apps.remove_member(app_id, user_id)
    return Response(status_code=204)


@router.get("/apps/{app_id}/keys", response_model=list[AppKeyOut])
async def list_keys(app_id: UUID, state: AppState = Depends(get_state)):
    await state.apps.get(app_id)
    return [AppKeyOut.model_validate(k, from_attributes=True) for k in await state.apps.keys(app_id)]


@router.post("/apps/{app_id}/keys", response_model=AppKeyCreated, status_code=201)
async def create_key(
    app_id: UUID, body: AppKeyCreate, p: Principal = Depends(admin), state: AppState = Depends(get_state)
):
    key, raw = await state.apps.create_key(p.user, app_id, body.name)
    return AppKeyCreated(**AppKeyOut.model_validate(key, from_attributes=True).model_dump(), key=raw)


@router.delete("/apps/{app_id}/keys/{key_id}", status_code=204)
async def revoke_key(app_id: UUID, key_id: UUID, state: AppState = Depends(get_state)):
    await state.apps.revoke_key(app_id, key_id)
    return Response(status_code=204)
