"""Sign-in, profile, credits and plans for an app's end users (e.g. people using Reelify).

Every call sends the app's `X-App-Key` (and `X-Device-Id`). After sign-in, calls also send the
user's session as `Authorization: Bearer cas_...`."""

from fastapi import APIRouter, Depends, Request, Response

from studio.api.auth import client_ip
from studio.api.schemas import (
    AppClientConfig,
    AppInfo,
    AppUserOut,
    CreditEntryOut,
    FirebaseSignInIn,
    GoogleSignInIn,
    MeUpdate,
    OtpSendIn,
    OtpSendOut,
    OtpVerifyIn,
    PaymentConfig,
    PlanOut,
    PlanRef,
    SignInMethods,
    SignInOut,
    SubscriptionOut,
)
from studio.apps.service import AppPrincipal
from studio.deps import AppState, app_key, get_state, signed_in_app_user
from studio.endusers.service import SignIn

router = APIRouter(prefix="/v1/app", tags=["app clients: sign-in and account"])


# ---- serializers (also used by the admin console) ------------------------------------------------


def subscription_out(sub, plan) -> SubscriptionOut:
    return SubscriptionOut(
        id=sub.id,
        plan=PlanRef(id=plan.id, slug=plan.slug, name=plan.name),
        status=sub.status,
        provider=sub.provider,
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        next_credit_grant_at=sub.next_credit_grant_at,
        created_at=sub.created_at,
    )


def user_fields(user, active: tuple | None) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
        "photo_url": user.photo_url,
        "sign_in": "google" if user.google_sub else "phone",
        "credits": user.credits,
        "subscription": subscription_out(*active) if active else None,
        "created_at": user.created_at,
    }


async def me_out(state: AppState, user) -> AppUserOut:
    active = (await state.billing.active_subscriptions([user.id])).get(user.id)
    return AppUserOut(**user_fields(user, active))


def entry_out(e) -> CreditEntryOut:
    return CreditEntryOut(
        id=e.id, delta=e.delta, reason=e.reason, note=e.note, job_id=e.job_id, created_at=e.created_at
    )


def plan_out(p) -> PlanOut:
    return PlanOut(
        id=p.id,
        slug=p.slug,
        name=p.name,
        description=p.description,
        price_minor=p.price_minor,
        currency=p.currency,
        billing_period=p.billing_period,
        credits_per_month=p.credits_per_month,
        badge=p.badge,
    )


async def sign_in_out(state: AppState, r: SignIn) -> SignInOut:
    return SignInOut(
        token=r.token, expires_at=r.expires_at, is_new=r.is_new, user=await me_out(state, r.user)
    )


# ---- routes -------------------------------------------------------------------------------------


@router.get("", response_model=AppClientConfig)
async def app_config(a: AppPrincipal = Depends(app_key)):
    """Call on start: which sign-in buttons to show, and whether sign-in is needed for templates."""
    app = a.app
    return AppClientConfig(
        app=AppInfo(slug=app.slug, name=app.name, description=app.description, platform=app.platform),
        sign_in=SignInMethods(
            google=app.auth_google_enabled,
            phone=app.auth_phone_enabled,
            google_client_id=(app.google_client_ids or [None])[0] if app.auth_google_enabled else None,
            phone_provider=app.phone_provider if app.auth_phone_enabled else None,
            firebase_project_id=app.firebase_project_id
            if app.auth_phone_enabled and app.phone_provider == "firebase"
            else None,
        ),
        require_login=app.require_login,
        payments=PaymentConfig(
            provider=app.payment_provider,
            mode=app.payment_mode,
            razorpay_key_id=app.razorpay_key_id if app.payment_provider == "razorpay" else None,
        ),
    )


@router.post("/auth/google", response_model=SignInOut)
async def sign_in_google(
    body: GoogleSignInIn, a: AppPrincipal = Depends(app_key), state: AppState = Depends(get_state)
):
    """Exchange a Google ID token (Credential Manager, requested for this app's Web client id) for
    a session. Creates the account on first sign-in."""
    return await sign_in_out(state, await state.endusers.sign_in_google(a.app, body.id_token, a.device_id))


@router.post("/auth/firebase", response_model=SignInOut)
async def sign_in_firebase(
    body: FirebaseSignInIn, a: AppPrincipal = Depends(app_key), state: AppState = Depends(get_state)
):
    """Exchange the Firebase ID token of a phone sign-in (Firebase Auth on the device) for a session.
    Only when `sign_in.phone_provider` is `firebase`. Creates the account on first sign-in."""
    r = await state.endusers.sign_in_firebase(a.app, body.id_token, a.device_id)
    return await sign_in_out(state, r)


@router.post("/auth/otp/send", response_model=OtpSendOut)
async def otp_send(
    body: OtpSendIn,
    request: Request,
    a: AppPrincipal = Depends(app_key),
    state: AppState = Depends(get_state),
):
    """Text a 6-digit code to the number. Limited per number, device and network (429)."""
    ch, phone = await state.endusers.send_otp(a.app, body.phone, a.device_id, client_ip(request))
    st = state.settings
    return OtpSendOut(
        challenge_id=ch.id, phone=phone, expires_in_s=st.otp_ttl_s, resend_after_s=st.otp_resend_after_s
    )


@router.post("/auth/otp/verify", response_model=SignInOut)
async def otp_verify(
    body: OtpVerifyIn, a: AppPrincipal = Depends(app_key), state: AppState = Depends(get_state)
):
    """Check the code; on success, a session (and the account on first sign-in)."""
    r = await state.endusers.verify_otp(a.app, body.challenge_id, body.code, a.device_id)
    return await sign_in_out(state, r)


@router.post("/auth/logout", status_code=204)
async def logout(
    request: Request, _: AppPrincipal = Depends(signed_in_app_user), state: AppState = Depends(get_state)
):
    await state.endusers.logout(request.headers["authorization"][7:].strip())
    return Response(status_code=204)


@router.get("/me", response_model=AppUserOut)
async def me(a: AppPrincipal = Depends(signed_in_app_user), state: AppState = Depends(get_state)):
    """The signed-in user, their credit balance and active subscription."""
    return await me_out(state, a.user)


@router.patch("/me", response_model=AppUserOut)
async def update_me(
    body: MeUpdate, a: AppPrincipal = Depends(signed_in_app_user), state: AppState = Depends(get_state)
):
    return await me_out(state, await state.endusers.rename(a.user, body.name))


@router.delete("/me", status_code=204)
async def delete_me(a: AppPrincipal = Depends(signed_in_app_user), state: AppState = Depends(get_state)):
    """Delete the account: personal data is removed and every session ends. Remaining credits are lost."""
    await state.endusers.delete_account(a.user)
    return Response(status_code=204)


@router.get("/me/credits", response_model=list[CreditEntryOut])
async def my_credits(
    limit: int = 50, a: AppPrincipal = Depends(signed_in_app_user), state: AppState = Depends(get_state)
):
    """Credit history, newest first: grants, generations, refunds."""
    return [entry_out(e) for e in await state.billing.history(a.user.id, limit)]


@router.get("/plans", response_model=list[PlanOut])
async def plans(a: AppPrincipal = Depends(app_key), state: AppState = Depends(get_state)):
    """The app's plans, in display order (for the Subscribe screen)."""
    return [plan_out(p) for p in await state.billing.plans(a.app.id, active_only=True)]
