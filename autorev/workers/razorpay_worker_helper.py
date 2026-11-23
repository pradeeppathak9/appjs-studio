"""
Razorpay background tasks: collect subscriptions as they come due, and settle
charges whose webhook never arrived. The logic is app.razorpay_billing; this
module only walks the apps and holds the single-flight lock.

Each public function maps 1:1 to a Celery task in phone_worker.py.
"""
import logging

from app import razorpay_billing as billing
from app.api_handler.razorpay import RazorpayAPIHandler
from app.database import SessionLocal
from app.models.app import App
from app.models.razorpay import RazorpayApp
from phone_worker_helper import _single_flight

logger = logging.getLogger("autorev.worker")

# Longer than a run can take, short enough that a killed worker does not stall
# collection for long.
LOCK_TTL_SECONDS = 50 * 60


def _razorpay_apps(db):
    """Enabled apps with Razorpay switched on and both keys saved."""
    return (
        db.query(App, RazorpayApp)
        .join(RazorpayApp, RazorpayApp.app_id == App.id)
        .filter(
            App.enabled.is_(True),
            App.razorpay_enabled.is_(True),
            RazorpayApp.razorpay_key_id.isnot(None),
            RazorpayApp.razorpay_key_secret.isnot(None),
        )
        .all()
    )


def _for_each_app(name: str, fn):
    with _single_flight(f"lock:{name}", LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            logger.info(f"{name}: another run holds the lock, skipping")
            return
        db = SessionLocal()
        try:
            for app, detail in _razorpay_apps(db):
                handler = RazorpayAPIHandler(detail.razorpay_key_id, detail.razorpay_key_secret)
                try:
                    counts = fn(db, handler, app.id)
                    logger.info(f"{name} app={app.id}: {counts}")
                except Exception:
                    db.rollback()
                    logger.exception(f"{name} failed for app={app.id}")
        finally:
            db.close()


def _collect_razorpay_due():
    _for_each_app("razorpay-collect-due", billing.collect_due)


def _reconcile_razorpay():
    _for_each_app("razorpay-reconcile", billing.reconcile)
