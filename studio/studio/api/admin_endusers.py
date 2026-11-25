"""Admin dashboard for an app's end users: plans, users, credits and (manual) subscriptions.
Sign-in settings are part of the app itself (PUT /v1/admin/apps/{app_id})."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from studio.api.client_auth import entry_out, subscription_out, user_fields
from studio.api.schemas import (
    AppUserAdminOut,
    AppUserDetail,
    AppUserPage,
    AppUserStatusIn,
    CreditAdjustIn,
    CreditBalance,
    CreditEntryPage,
    PlanAdminOut,
    PlanOrderIn,
    SubscriptionAdminOut,
    SubscriptionGrantIn,
    SubscriptionLinkIn,
    SubscriptionOut,
)
from studio.auth.service import Principal
from studio.deps import AppState, admin, get_state
from studio.endusers.billing import PlanCreate, PlanFields

router = APIRouter(prefix="/v1/admin/apps/{app_id}", tags=["admin: app users"], dependencies=[Depends(admin)])


def plan_admin_out(p) -> PlanAdminOut:
    return PlanAdminOut.model_validate(p, from_attributes=True)


def user_admin_out(u, active, trial_used: bool = False) -> AppUserAdminOut:
    return AppUserAdminOut(**user_fields(u, active, trial_used), status=u.status, last_seen_at=u.last_seen_at)


def subscription_admin_out(sub, plan) -> SubscriptionAdminOut:
    return SubscriptionAdminOut(
        **subscription_out(sub, plan).model_dump(),
        provider_ref=sub.provider_ref,
    )


async def user_detail(state: AppState, u) -> AppUserDetail:
    subs = await state.billing.subscriptions(u.id)
    active = next(((s, p) for s, p in subs if s.status == "active"), None)
    return AppUserDetail(
        **user_admin_out(u, active, any(s.is_trial for s, _ in subs)).model_dump(),
        subscriptions=[subscription_admin_out(s, p) for s, p in subs],
        ledger=[entry_out(e) for e in await state.billing.history(u.id, 100)],
    )


# ---- plans --------------------------------------------------------------------------------------------


@router.get("/plans", response_model=list[PlanAdminOut])
async def list_plans(app_id: UUID, state: AppState = Depends(get_state)):
    await state.apps.get(app_id)
    return [plan_admin_out(p) for p in await state.billing.plans(app_id)]


@router.post("/plans", response_model=PlanAdminOut, status_code=201)
async def create_plan(app_id: UUID, body: PlanCreate, state: AppState = Depends(get_state)):
    await state.apps.get(app_id)
    return plan_admin_out(await state.billing.create_plan(app_id, body))


@router.put("/plans/order", status_code=204)
async def order_plans(app_id: UUID, body: PlanOrderIn, state: AppState = Depends(get_state)):
    await state.billing.reorder_plans(app_id, body.plan_ids)
    return Response(status_code=204)


@router.put("/plans/{plan_id}", response_model=PlanAdminOut)
async def update_plan(app_id: UUID, plan_id: UUID, body: PlanFields, state: AppState = Depends(get_state)):
    """Price and credit changes apply from the next monthly grant."""
    return plan_admin_out(await state.billing.update_plan(app_id, plan_id, body))


@router.delete("/plans/{plan_id}", status_code=204)
async def delete_plan(app_id: UUID, plan_id: UUID, state: AppState = Depends(get_state)):
    """Deletes a plan nobody subscribed to; archives it otherwise."""
    await state.billing.delete_plan(app_id, plan_id)
    return Response(status_code=204)


# ---- users ---------------------------------------------------------------------------------------------


@router.get("/users", response_model=AppUserPage)
async def list_users(
    app_id: UUID,
    q: str | None = Query(None, max_length=200, description="search name, email, phone, or a user id"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: AppState = Depends(get_state),
):
    """The app's users, newest first, a page at a time, with the total that match."""
    await state.apps.get(app_id)
    users, total = await state.endusers.page(app_id, q, limit, offset)
    active = await state.billing.active_subscriptions([u.id for u in users])
    trials = await state.billing.trial_users([u.id for u in users])
    return AppUserPage(
        items=[user_admin_out(u, active.get(u.id), u.id in trials) for u in users],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/users/{user_id}", response_model=AppUserDetail)
async def get_user(app_id: UUID, user_id: UUID, state: AppState = Depends(get_state)):
    return await user_detail(state, await state.endusers.get(app_id, user_id))


@router.get("/users/{user_id}/credits", response_model=CreditEntryPage)
async def credit_history(
    app_id: UUID,
    user_id: UUID,
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    state: AppState = Depends(get_state),
):
    """The user's credit transactions (generations, refunds, plan grants, manual changes), newest first."""
    user = await state.endusers.get(app_id, user_id)
    entries, total = await state.billing.history_page(user.id, limit, offset)
    return CreditEntryPage(items=[entry_out(e) for e in entries], total=total, limit=limit, offset=offset)


@router.put("/users/{user_id}/status", response_model=AppUserDetail)
async def set_user_status(
    app_id: UUID, user_id: UUID, body: AppUserStatusIn, state: AppState = Depends(get_state)
):
    """Block (signs them out everywhere and refuses their calls) or unblock a user."""
    return await user_detail(state, await state.endusers.set_status(app_id, user_id, body.status))


@router.post("/users/{user_id}/credits", response_model=CreditBalance)
async def adjust_credits(
    app_id: UUID,
    user_id: UUID,
    body: CreditAdjustIn,
    p: Principal = Depends(admin),
    state: AppState = Depends(get_state),
):
    """Add or remove credits by hand, with a note (kept in the user's history)."""
    user = await state.endusers.get(app_id, user_id)
    return CreditBalance(credits=await state.billing.adjust(p.user, user, body.delta, body.note))


@router.post("/users/{user_id}/subscriptions", response_model=SubscriptionOut, status_code=201)
async def grant_subscription(
    app_id: UUID,
    user_id: UUID,
    body: SubscriptionGrantIn,
    p: Principal = Depends(admin),
    state: AppState = Depends(get_state),
):
    """Give a plan without payment (until payments are wired in): starts now and grants the first
    month's credits; later months are granted automatically."""
    user = await state.endusers.get(app_id, user_id)
    sub = await state.billing.grant_subscription(p.user, user, body.plan_id)
    return subscription_out(sub, await state.billing.plan(app_id, sub.plan_id))


@router.delete("/users/{user_id}/subscriptions/{subscription_id}", status_code=204)
async def cancel_subscription(
    app_id: UUID, user_id: UUID, subscription_id: UUID, state: AppState = Depends(get_state)
):
    """Stop now; no more monthly credits. Credits already granted stay."""
    await state.billing.cancel_subscription(app_id, user_id, subscription_id)
    return Response(status_code=204)


@router.put("/users/{user_id}/subscriptions/{subscription_id}/link", response_model=SubscriptionAdminOut)
async def link_subscription(
    app_id: UUID,
    user_id: UUID,
    subscription_id: UUID,
    body: SubscriptionLinkIn,
    state: AppState = Depends(get_state),
):
    """Link the subscription to its payment-gateway subscription (Razorpay or PhonePe id), or back to
    `manual`. Until payments are wired in, this records a subscription paid outside the app."""
    sub, plan = await state.billing.link_subscription(
        app_id, user_id, subscription_id, body.provider, body.provider_ref
    )
    return subscription_admin_out(sub, plan)
