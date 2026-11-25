"""What an integration (and the console) needs to know about this server and an app.

  * GET /api/config               public: the gateways this server offers (AUTOREV_GATEWAYS)
  * GET /api/v1/{app_id}/config   app API key: the app's gateways and their public settings, so an
                                  integration such as AppJs Studio can check its connection and
                                  hand Razorpay Checkout the right key id
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import App, PhonePeApp, RazorpayApp
from app.router.razorpay_router import get_app

router = APIRouter(tags=["integration"])


@router.get("/api/config")
def server_config():
    return {"gateways": settings.enabled_gateways}


@router.get("/api/v1/{app_id}/config")
def app_config(app: App = Depends(get_app), db: Session = Depends(get_db)):
    """The app's gateways that are switched on and offered here, with public settings only."""
    gateways = {}
    if app.razorpay_enabled and settings.gateway_on("razorpay"):
        rz = db.query(RazorpayApp).filter(RazorpayApp.app_id == app.id).first()
        gateways["razorpay"] = {
            "key_id": rz.razorpay_key_id if rz else None,
            "environment": (rz.razorpay_environment if rz else None) or "TEST",
            "ready": bool(rz and rz.razorpay_key_id and rz.razorpay_key_secret),
        }
    if app.phonepe_enabled and settings.gateway_on("phonepe"):
        pp = db.query(PhonePeApp).filter(PhonePeApp.app_id == app.id).first()
        gateways["phonepe"] = {
            "environment": getattr(pp, "phonepe_environment", None),
            "ready": bool(pp and getattr(pp, "phonepe_client_id", None)),
        }
    return {
        "app_id": app.id,
        "name": app.name,
        "enabled": app.enabled,
        "gateways": gateways,
        "webhook": {"enabled": bool(app.webhook_enabled and app.webhook_url and app.webhook_secret)},
    }
