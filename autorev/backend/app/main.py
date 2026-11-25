import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import Base, engine
from app.setup import ensure_setup_token
from app.router.admin import router as admin_router
from app.router.auth import router as auth_router
from app.router.apps import router as apps_router
from app.router.dashboard import router as dashboard_router
from app.router.integration_router import router as integration_router
from app.router.phonepe_router import router as subscription_router
from app.router.razorpay_router import router as razorpay_subscription_router
from app.router.redis_router import router as redis_admin_router
from app.router.tasks_router import router as tasks_router
from app.router.webhooks_router import router as webhooks_router


log = logging.getLogger("autorev")


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if token := ensure_setup_token():
        log.warning("First-run setup: open /setup and use setup token %s", token)
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
if settings.gateway_on("phonepe"):
    app.include_router(subscription_router)
if settings.gateway_on("razorpay"):
    app.include_router(razorpay_subscription_router)
app.include_router(integration_router)
app.include_router(redis_admin_router)
app.include_router(tasks_router)
app.include_router(webhooks_router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
