import secrets

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import App, AppUser, PhonePeApp, RazorpayApp, User
from app.api_handler.phonepe import PHONEPE_URLS, _fetch_token
from app.schemas import AppResponse, AppUpdate

router = APIRouter(prefix="/api/apps", tags=["apps"])


def _get_accessible_app(app_id: str, user: User, db: Session) -> App:
    """Resolve an app the caller may use, by grant — admins included.

    is_admin used to bypass this, which made the grants on an admin account
    decorative: Admin → Users could show 7 apps while the dashboard listed all
    11. Admin power now lives entirely in /api/admin, which is where apps are
    administered from; this is the customer-facing surface and it answers the
    same question for everyone. An admin who needs an app on their own
    dashboard grants it to themselves under Admin → Users → Manage Apps.
    """
    app = (
        db.query(App)
        .join(AppUser, (AppUser.app_id == App.id) & (AppUser.user_id == user.id))
        .filter(App.id == app_id)
        .first()
    )
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    return app


def _gateway_detail_maps(app_ids: list[str], db: Session):
    """Fetch the PhonePe/Razorpay side tables for many apps in two queries.

    Building responses one app at a time issues two extra queries per app; list
    endpoints render every app the caller can see, so that is 2N round trips for
    rows that come back in one.
    """
    if not app_ids:
        return {}, {}
    phonepe = {
        d.app_id: d
        for d in db.query(PhonePeApp).filter(PhonePeApp.app_id.in_(app_ids)).all()
    }
    razorpay = {
        d.app_id: d
        for d in db.query(RazorpayApp).filter(RazorpayApp.app_id.in_(app_ids)).all()
    }
    return phonepe, razorpay


def _to_app_response(app: App, db: Session, phonepe_map=None, razorpay_map=None) -> AppResponse:
    if phonepe_map is None:
        phonepe_detail = db.query(PhonePeApp).filter(PhonePeApp.app_id == app.id).first()
    else:
        phonepe_detail = phonepe_map.get(app.id)
    if razorpay_map is None:
        razorpay_detail = db.query(RazorpayApp).filter(RazorpayApp.app_id == app.id).first()
    else:
        razorpay_detail = razorpay_map.get(app.id)
    return AppResponse(
        id=app.id,
        slug=app.slug,
        name=app.name,
        phonepe_enabled=app.phonepe_enabled,
        razorpay_enabled=app.razorpay_enabled,
        phonepe_client_id=phonepe_detail.phonepe_client_id if phonepe_detail else None,
        phonepe_client_secret=phonepe_detail.phonepe_client_secret if phonepe_detail else None,
        phonepe_merchant_id=phonepe_detail.phonepe_merchant_id if phonepe_detail else None,
        phonepe_environment=phonepe_detail.phonepe_environment if phonepe_detail else "UAT",
        razorpay_key_id=razorpay_detail.razorpay_key_id if razorpay_detail else None,
        razorpay_key_secret=razorpay_detail.razorpay_key_secret if razorpay_detail else None,
        razorpay_webhook_secret=razorpay_detail.razorpay_webhook_secret if razorpay_detail else None,
        razorpay_environment=razorpay_detail.razorpay_environment if razorpay_detail else "TEST",
        api_key=app.api_key,
        enabled=app.enabled,
        trial_enabled=phonepe_detail.trial_enabled if phonepe_detail else False,
        trial_amount=phonepe_detail.trial_amount if phonepe_detail else None,
        trial_period_days=phonepe_detail.trial_period_days if phonepe_detail else None,
    )


@router.get("", response_model=list[AppResponse])
def list_apps(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Grants decide this for every account, admins included — see
    # _get_accessible_app. The full catalogue is at GET /api/admin/apps.
    apps = (
        db.query(App)
        .join(AppUser, (AppUser.app_id == App.id) & (AppUser.user_id == current_user.id))
        .order_by(App.created_at.desc())
        .all()
    )
    phonepe_map, razorpay_map = _gateway_detail_maps([a.id for a in apps], db)
    return [_to_app_response(a, db, phonepe_map, razorpay_map) for a in apps]


@router.get("/{app_id}", response_model=AppResponse)
def get_app(
    app_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = _get_accessible_app(app_id, current_user, db)
    return _to_app_response(app, db)


@router.patch("/{app_id}", response_model=AppResponse)
def update_app(
    app_id: str,
    body: AppUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = _get_accessible_app(app_id, current_user, db)
    data = body.model_dump(exclude_none=True)

    app_fields = {"name"}
    trial_fields = {"trial_enabled", "trial_amount", "trial_period_days"}  # PhonePe-only
    phonepe_fields = {k[len("phonepe_"):]: v for k, v in data.items() if k.startswith("phonepe_")}
    razorpay_fields = {k[len("razorpay_"):]: v for k, v in data.items() if k.startswith("razorpay_")}
    trial_updates = {k: v for k, v in data.items() if k in trial_fields}

    for field, value in data.items():
        if field in app_fields:
            setattr(app, field, value)

    if phonepe_fields or trial_updates:
        detail = db.query(PhonePeApp).filter(PhonePeApp.app_id == app.id).first()
        if detail:
            for field, value in phonepe_fields.items():
                setattr(detail, f"phonepe_{field}", value)
            for field, value in trial_updates.items():
                setattr(detail, field, value)

    if razorpay_fields:
        detail = db.query(RazorpayApp).filter(RazorpayApp.app_id == app.id).first()
        if detail:
            for field, value in razorpay_fields.items():
                setattr(detail, f"razorpay_{field}", value)

    db.commit()
    db.refresh(app)
    return _to_app_response(app, db)


@router.post("/{app_id}/test-phonepe")
def test_phonepe(
    app_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.api_handler.phonepe import PhonePeAPIHandler, PhonePeException

    app = _get_accessible_app(app_id, current_user, db)
    detail = db.query(PhonePeApp).filter(PhonePeApp.app_id == app.id).first()
    if not detail or not detail.phonepe_client_id or not detail.phonepe_client_secret:
        return {"success": False, "stage": "credentials", "error": "PhonePe credentials not configured"}

    env = detail.phonepe_environment or "UAT"
    identity_url = PHONEPE_URLS[env]["identity"]

    # Stage 1: OAuth token fetch
    try:
        _fetch_token(detail.phonepe_client_id, detail.phonepe_client_secret, identity_url)
    except httpx.HTTPStatusError as e:
        try:
            msg = e.response.json().get("message", f"HTTP {e.response.status_code}")
        except Exception:
            msg = f"HTTP {e.response.status_code}"
        return {"success": False, "stage": "oauth", "error": f"Authentication failed: {msg}"}
    except Exception as e:
        return {"success": False, "stage": "oauth", "error": f"Connection error: {str(e)}"}

    # Stage 2: Subscription API access — dummy status call; 404 = API reachable, 401 = not provisioned
    handler = PhonePeAPIHandler(
        app_id=app.id,
        client_id=detail.phonepe_client_id,
        client_secret=detail.phonepe_client_secret,
        environment=env,
        custom=True,
    )
    try:
        handler.subscription_status("autorev-test-probe")
        return {"success": True, "environment": env}
    except PhonePeException as e:
        if e.status_code in (401, 403):
            return {
                "success": False,
                "stage": "api_access",
                "error": (
                    f"OAuth succeeded but Subscription API returned {e.status_code}. "
                    f"Your PhonePe merchant account may not have subscription API access enabled in {env}."
                ),
            }
        # Any other error (404, 400 "No Subscription found", etc.) means OAuth worked and the
        # API is reachable — the probe ID just doesn't exist, which is expected.
        return {"success": True, "environment": env}
    except Exception as e:
        return {"success": False, "stage": "api_call", "error": str(e)}


@router.post("/{app_id}/test-razorpay")
def test_razorpay(
    app_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.api_handler.razorpay import RazorpayAPIHandler, RazorpayException

    app = _get_accessible_app(app_id, current_user, db)
    detail = db.query(RazorpayApp).filter(RazorpayApp.app_id == app.id).first()
    if not detail or not detail.razorpay_key_id or not detail.razorpay_key_secret:
        return {"success": False, "stage": "credentials", "error": "Razorpay credentials not configured"}

    handler = RazorpayAPIHandler(key_id=detail.razorpay_key_id, key_secret=detail.razorpay_key_secret)
    try:
        handler._request("GET", "/payments", params={"count": 1})
        return {"success": True, "environment": detail.razorpay_environment or "TEST"}
    except RazorpayException as e:
        if e.status_code == 401:
            return {"success": False, "stage": "auth", "error": "Invalid Razorpay key_id/key_secret"}
        return {"success": False, "stage": "api_call", "error": str(e)}
    except Exception as e:
        return {"success": False, "stage": "api_call", "error": f"Connection error: {str(e)}"}


@router.post("/{app_id}/reset-key", response_model=AppResponse)
def reset_api_key(
    app_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    app = _get_accessible_app(app_id, current_user, db)
    app.api_key = secrets.token_hex(32)
    db.commit()
    db.refresh(app)
    return _to_app_response(app, db)
