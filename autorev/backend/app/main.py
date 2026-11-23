import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import hash_password
from app.config import settings
from app.database import Base, engine, SessionLocal
from app.models import User
from app.router.admin import router as admin_router
from app.router.auth import router as auth_router
from app.router.apps import router as apps_router
from app.router.dashboard import router as dashboard_router
from app.router.phonepe_router import router as subscription_router
from app.router.razorpay_router import router as razorpay_subscription_router
from app.router.redis_router import router as redis_admin_router
from app.router.tasks_router import router as tasks_router
from app.router.webhooks_router import router as webhooks_router


def _seed_admin():
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.is_admin == True).first():
            admin = User(
                email=settings.admin_email,
                hashed_password=hash_password(settings.admin_password),
                full_name="Admin",
                is_admin=True,
            )
            db.add(admin)
            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _seed_admin()
    yield


app = FastAPI(
    title="AutoRev API",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Response headers are hidden from cross-origin JS unless named here; the
    # dashboard reads X-Total-Count to size its pagers.
    expose_headers=["X-Total-Count"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(apps_router)
app.include_router(dashboard_router)
app.include_router(subscription_router)
app.include_router(razorpay_subscription_router)
app.include_router(redis_admin_router)
app.include_router(tasks_router)
app.include_router(webhooks_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
