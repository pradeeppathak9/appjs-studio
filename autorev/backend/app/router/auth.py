import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import setup as first_run
from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.models import User
from app.redis import redis_client
from app.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    SetupRequest,
    SetupResponse,
    SetupState,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/setup", response_model=SetupState)
def setup_state(db: Session = Depends(get_db)):
    return SetupState(needed=first_run.setup_needed(db))


@router.post("/setup", response_model=SetupResponse, status_code=status.HTTP_201_CREATED)
def setup(body: SetupRequest, db: Session = Depends(get_db)):
    """First run: create the first admin with the setup token, and sign them in."""
    try:
        user = first_run.create_first_admin(db, body.setup_token, body.email, body.full_name, body.password)
    except first_run.SetupForbidden as e:
        raise HTTPException(status_code=403, detail=str(e))
    except first_run.AlreadySetUp as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = create_access_token({"sub": str(user.id)})
    return SetupResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({"sub": str(user.id)})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    cache_key = f"user:{current_user.id}"
    cached = redis_client.get(cache_key)
    if cached:
        return UserResponse.model_validate_json(cached)

    response = UserResponse.model_validate(current_user)
    redis_client.setex(cache_key, 300, response.model_dump_json())
    return response


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.hashed_password = hash_password(body.new_password)
    db.commit()
