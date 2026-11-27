import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.auth import get_current_admin_user, hash_password
from app.database import get_db
from app.models import App, AppUser, PhonePeApp, RazorpayApp, User
from app.schemas import (
    AdminAppCreate,
    AdminAppGrantUser,
    AdminAppResponse,
    AdminAppUpdate,
    AdminUserAppResponse,
    AdminUserCreate,
    AdminUserResponse,
    AdminUserUpdate,
    AppUserResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _primary_admin_id(db: Session) -> int | None:
    """The first admin: the one /setup created (or, on older deployments, the seeded one)."""
    return db.query(func.min(User.id)).filter(User.is_admin.is_(True)).scalar()


def _is_protected(user: User, db: Session) -> bool:
    """The primary admin account, which must stay an admin.

    Demoting or deleting it could leave nobody able to reach /api/admin at all,
    and setup only reopens when no admin is left, so nothing in the product
    could undo that cleanly.
    """
    return user.id == _primary_admin_id(db)


def _user_response(user: User, apps_count: int = 0, *, protected: bool = False) -> AdminUserResponse:
    r = AdminUserResponse.model_validate(user)
    r.apps_count = apps_count
    r.is_protected = protected
    return r


# ── Users ──────────────────────────────────────────────────────────────────────

@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    counts = dict(
        db.query(AppUser.user_id, func.count(AppUser.app_id))
        .group_by(AppUser.user_id)
        .all()
    )
    users = db.query(User).order_by(User.created_at.desc()).all()
    primary = _primary_admin_id(db)
    return [_user_response(u, counts.get(u.id, 0), protected=u.id == primary) for u in users]


@router.post("/users", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: AdminUserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        is_admin=body.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _user_response(user, protected=_is_protected(user, db))


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
def update_user(
    user_id: int,
    body: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    data = body.model_dump(exclude_none=True)
    password = data.pop("password", None)

    if "email" in data and data["email"] != user.email:
        if db.query(User).filter(User.email == data["email"]).first():
            raise HTTPException(status_code=400, detail="Email already registered")
        # Renaming the protected account would move it out from under the rule
        # above, which is demotion by another route.
        if _is_protected(user, db):
            raise HTTPException(
                status_code=400,
                detail="The primary admin account's email cannot be changed",
            )

    if data.get("is_admin") is False:
        if _is_protected(user, db):
            raise HTTPException(
                status_code=400, detail="The primary admin account must stay an admin"
            )
        # Nobody can sign away their own access: the demotion takes effect on the
        # next request and there may be no other admin left to undo it.
        if user.id == current_admin.id:
            raise HTTPException(
                status_code=400, detail="You cannot remove your own admin access"
            )

    for field, value in data.items():
        setattr(user, field, value)
    if password:
        user.hashed_password = hash_password(password)

    db.commit()
    db.refresh(user)
    return _user_response(user, protected=_is_protected(user, db))


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    if user_id == current_admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if _is_protected(user, db):
        raise HTTPException(
            status_code=400, detail="The primary admin account cannot be deleted"
        )

    db.delete(user)
    db.commit()


# ── Apps ───────────────────────────────────────────────────────────────────────

def new_app_id() -> str:
    """16 hex chars (64 random bits): short enough to read and paste, ample for a few apps."""
    return secrets.token_hex(8)


def _admin_app_maps(app_ids: list[str], db: Session):
    """Side tables and owner emails for many apps, in three queries instead of 3N."""
    if not app_ids:
        return {}, {}, {}
    phonepe = {
        d.app_id: d
        for d in db.query(PhonePeApp).filter(PhonePeApp.app_id.in_(app_ids)).all()
    }
    razorpay = {
        d.app_id: d
        for d in db.query(RazorpayApp).filter(RazorpayApp.app_id.in_(app_ids)).all()
    }
    # The owner is the earliest AppUser grant; ordering ascending and keeping the
    # first row seen per app reproduces the per-app "ORDER BY created_at ASC LIMIT 1".
    owners: dict[str, str] = {}
    rows = (
        db.query(AppUser.app_id, User.email)
        .join(User, User.id == AppUser.user_id)
        .filter(AppUser.app_id.in_(app_ids))
        .order_by(AppUser.created_at.asc())
        .all()
    )
    for app_id, email in rows:
        owners.setdefault(app_id, email)
    return phonepe, razorpay, owners


def _to_admin_app_response(
    app: App, db: Session, phonepe_map=None, razorpay_map=None, owner_map=None
) -> AdminAppResponse:
    if phonepe_map is None:
        phonepe_detail = db.query(PhonePeApp).filter(PhonePeApp.app_id == app.id).first()
    else:
        phonepe_detail = phonepe_map.get(app.id)
    if razorpay_map is None:
        razorpay_detail = db.query(RazorpayApp).filter(RazorpayApp.app_id == app.id).first()
    else:
        razorpay_detail = razorpay_map.get(app.id)
    if owner_map is None:
        owner_row = (
            db.query(User.email)
            .join(AppUser, AppUser.user_id == User.id)
            .filter(AppUser.app_id == app.id)
            .order_by(AppUser.created_at.asc())
            .first()
        )
        owner_email = owner_row[0] if owner_row else None
    else:
        owner_email = owner_map.get(app.id)
    return AdminAppResponse(
        id=app.id,
        slug=app.slug,
        name=app.name,
        owner_email=owner_email,
        phonepe_enabled=app.phonepe_enabled,
        razorpay_enabled=app.razorpay_enabled,
        phonepe_environment=phonepe_detail.phonepe_environment if phonepe_detail else "UAT",
        razorpay_environment=razorpay_detail.razorpay_environment if razorpay_detail else "TEST",
        enabled=app.enabled,
        trial_enabled=phonepe_detail.trial_enabled if phonepe_detail else False,
        trial_amount=phonepe_detail.trial_amount if phonepe_detail else None,
        trial_period_days=phonepe_detail.trial_period_days if phonepe_detail else None,
        created_at=app.created_at,
    )


@router.get("/users/{user_id}/apps", response_model=list[AdminUserAppResponse])
def list_user_apps(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    """Every app, each flagged with whether this user can reach it.

    The whole catalogue rather than just the granted rows, because the caller is
    a "manage access" screen that has to offer the apps the user does *not*
    have. Returning both sides from one query also keeps the screen honest: a
    separate list-apps plus list-grants pair can interleave with another admin's
    change and render a checkbox state that never existed.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    granted = {
        au.app_id: au.created_at
        for au in db.query(AppUser).filter(AppUser.user_id == user_id).all()
    }
    apps = db.query(App).order_by(App.name).all()
    return [
        AdminUserAppResponse(
            app_id=a.id,
            slug=a.slug,
            name=a.name,
            phonepe_enabled=a.phonepe_enabled,
            razorpay_enabled=a.razorpay_enabled,
            enabled=a.enabled,
            granted=a.id in granted,
            granted_at=granted.get(a.id),
        )
        for a in apps
    ]


@router.get("/apps", response_model=list[AdminAppResponse])
def list_apps(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    apps = db.query(App).order_by(App.created_at.desc()).all()
    phonepe_map, razorpay_map, owner_map = _admin_app_maps([a.id for a in apps], db)
    return [
        _to_admin_app_response(a, db, phonepe_map, razorpay_map, owner_map) for a in apps
    ]


def _check_gateways_offered(*, phonepe: bool | None, razorpay: bool | None) -> None:
    """Refuse to switch on a gateway this server doesn't offer (AUTOREV_GATEWAYS)."""
    for name, on in (("phonepe", phonepe), ("razorpay", razorpay)):
        if on and not settings.gateway_on(name):
            label = {"phonepe": "PhonePe", "razorpay": "Razorpay"}[name]
            raise HTTPException(status_code=400, detail=f"{label} is not offered on this server")


@router.post("/apps", response_model=AdminAppResponse, status_code=status.HTTP_201_CREATED)
def create_app(
    body: AdminAppCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    owner = db.query(User).filter(User.id == body.user_id).first()
    if not owner:
        raise HTTPException(status_code=404, detail="User not found")

    phonepe_on = settings.gateway_on("phonepe")
    phonepe = body.phonepe_enabled if body.phonepe_enabled is not None else phonepe_on
    razorpay = body.razorpay_enabled if body.razorpay_enabled is not None else not phonepe_on
    _check_gateways_offered(phonepe=phonepe, razorpay=razorpay)
    if db.query(App.id).filter(App.slug == body.slug).first():
        raise HTTPException(status_code=409, detail="An app with this slug exists")

    app = App(
        id=new_app_id(),
        slug=body.slug,
        name=body.name,
        phonepe_enabled=phonepe,
        razorpay_enabled=razorpay,
        api_key=secrets.token_hex(32),
    )
    db.add(app)
    db.flush()  # get app.id before creating dependent rows

    if phonepe:
        db.add(PhonePeApp(app_id=app.id))
    if razorpay:
        db.add(RazorpayApp(app_id=app.id))

    # grant owner access — this AppUser row is also the only record of who owns the app
    db.add(AppUser(user_id=body.user_id, app_id=app.id))
    db.commit()
    db.refresh(app)
    return _to_admin_app_response(app, db)


@router.patch("/apps/{app_id}", response_model=AdminAppResponse)
def update_app(
    app_id: str,
    body: AdminAppUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    data = body.model_dump(exclude_none=True)
    _check_gateways_offered(phonepe=data.get("phonepe_enabled"), razorpay=data.get("razorpay_enabled"))
    trial_fields = {"trial_enabled", "trial_amount", "trial_period_days"}
    gateway_fields = {"phonepe_enabled", "razorpay_enabled"}

    for field, value in data.items():
        if field not in trial_fields and field not in gateway_fields:
            setattr(app, field, value)

    if "phonepe_enabled" in data:
        app.phonepe_enabled = data["phonepe_enabled"]
        if data["phonepe_enabled"] and not db.query(PhonePeApp).filter(PhonePeApp.app_id == app.id).first():
            db.add(PhonePeApp(app_id=app.id))

    if "razorpay_enabled" in data:
        app.razorpay_enabled = data["razorpay_enabled"]
        if data["razorpay_enabled"] and not db.query(RazorpayApp).filter(RazorpayApp.app_id == app.id).first():
            db.add(RazorpayApp(app_id=app.id))

    trial_updates = {k: v for k, v in data.items() if k in trial_fields}
    if trial_updates:
        detail = db.query(PhonePeApp).filter(PhonePeApp.app_id == app.id).first()
        if detail:  # trials only apply to PhonePe apps
            for field, value in trial_updates.items():
                setattr(detail, field, value)

    db.commit()
    db.refresh(app)
    return _to_admin_app_response(app, db)


@router.delete("/apps/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_app(
    app_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")
    db.delete(app)
    db.commit()


# ── App → User access ──────────────────────────────────────────────────────────

@router.get("/apps/{app_id}/users", response_model=list[AppUserResponse])
def list_app_users(
    app_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    rows = (
        db.query(AppUser, User)
        .join(User, User.id == AppUser.user_id)
        .filter(AppUser.app_id == app_id)
        .all()
    )
    return [
        AppUserResponse(
            user_id=u.id,
            email=u.email,
            full_name=u.full_name,
            is_admin=u.is_admin,
            created_at=au.created_at,
        )
        for au, u in rows
    ]


@router.post("/apps/{app_id}/users", response_model=AppUserResponse, status_code=status.HTTP_201_CREATED)
def grant_app_user(
    app_id: str,
    body: AdminAppGrantUser,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    app = db.query(App).filter(App.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    user = db.query(User).filter(User.id == body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    existing = db.query(AppUser).filter(
        AppUser.app_id == app_id, AppUser.user_id == body.user_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already has access")

    au = AppUser(user_id=body.user_id, app_id=app_id)
    db.add(au)
    db.commit()
    db.refresh(au)
    return AppUserResponse(
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_admin=user.is_admin,
        created_at=au.created_at,
    )


@router.delete("/apps/{app_id}/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_app_user(
    app_id: str,
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_admin_user),
):
    au = db.query(AppUser).filter(
        AppUser.app_id == app_id, AppUser.user_id == user_id
    ).first()
    if not au:
        raise HTTPException(status_code=404, detail="Access record not found")
    db.delete(au)
    db.commit()
