import os
import sys

# Ensure the workers directory is on the path for task-function lazy imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from celery import Celery
from celery.schedules import crontab

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/1")

celery_app = Celery("phone_worker", broker=CELERY_BROKER_URL)


@celery_app.task(name="phonepe-sync-subscription-state")
def sync_subscription_state_task():
    from phone_worker_helper import _sync_subscription_state
    _sync_subscription_state()


@celery_app.task(name="phonepe-sync-paused-state")
def sync_paused_state_task():
    from phone_worker_helper import _sync_paused_state
    _sync_paused_state()


@celery_app.task(name="phonepe-notify-redemption-due")
def notify_redemption_for_due_task():
    from phone_worker_helper import _notify_redemption_for_due_subscriptions
    _notify_redemption_for_due_subscriptions()


@celery_app.task(name="phonepe-sync-redemption-txn-state")
def sync_redemption_txn_state_task():
    from phone_worker_helper import _sync_redemption_txn_state
    _sync_redemption_txn_state()


@celery_app.task(name="phonepe-sync-scheduled-transactions")
def sync_scheduled_transactions_task():
    from phone_worker_helper import _sync_scheduled_transactions
    _sync_scheduled_transactions()


@celery_app.task(name="phonepe-advance-payment-dates")
def advance_payment_dates_task():
    from phone_worker_helper import _advance_payment_dates
    _advance_payment_dates()


@celery_app.task(name="phonepe-ensure-scheduled-transactions")
def ensure_scheduled_transactions_task():
    from phone_worker_helper import _ensure_scheduled_transactions
    _ensure_scheduled_transactions()


@celery_app.task(name="phonepe-sync-total-payments")
def sync_total_payments_task():
    from phone_worker_helper import _sync_total_payments
    _sync_total_payments()


@celery_app.task(name="phonepe-archive-failed-subscriptions")
def archive_failed_subscriptions_task():
    from phone_worker_helper import _archive_failed_subscriptions
    _archive_failed_subscriptions()


@celery_app.task(name="phonepe-revoke-duplicate-subscriptions")
def revoke_duplicate_subscriptions_task():
    from phone_worker_helper import _revoke_duplicate_active_subscriptions
    _revoke_duplicate_active_subscriptions()


@celery_app.task(name="razorpay-collect-due")
def razorpay_collect_due_task():
    from razorpay_worker_helper import _collect_razorpay_due
    _collect_razorpay_due()


@celery_app.task(name="razorpay-reconcile")
def razorpay_reconcile_task():
    from razorpay_worker_helper import _reconcile_razorpay
    _reconcile_razorpay()


# Delivery runs as its own task rather than inline in whatever observed the
# transition: customer endpoints hang, and that must not land in a request an
# integration is waiting on or stall a poll batch. acks_late keeps a delivery
# claimed-but-unsent if the worker dies mid-call — it will be re-run rather than
# lost, and the endpoint is expected to be idempotent on X-Autorev-Delivery.
@celery_app.task(name="autorev-webhook-deliver", bind=True, acks_late=True, max_retries=6)
def webhook_deliver_task(self, delivery_id):
    from phone_worker_helper import _deliver_webhook
    _deliver_webhook(self, delivery_id)


@celery_app.task(name="autorev-webhook-maintenance")
def webhook_maintenance_task():
    from phone_worker_helper import _webhook_maintenance
    _webhook_maintenance()


celery_app.conf.beat_schedule = {
    # Every 10 minutes
    "phonepe-sync-subscription-state-beat": {
        "task": "phonepe-sync-subscription-state",
        "schedule": 300.0,
    },

    # Every hour (staggered)
    "phonepe-notify-redemption-due-beat": {
        "task": "phonepe-notify-redemption-due",
        "schedule": crontab(minute=15),
    },
    "phonepe-sync-redemption-txn-state-beat": {
        "task": "phonepe-sync-redemption-txn-state",
        "schedule": crontab(minute=30),
    },
    "phonepe-sync-scheduled-transactions-beat": {
        "task": "phonepe-sync-scheduled-transactions",
        "schedule": crontab(minute=45),
    },

    # Razorpay, hourly. AutoRev collects Razorpay subscriptions itself: charges
    # start a day before the due date (Razorpay debits ~25h after its pre-debit
    # notice), and the reconcile pass settles any charge whose webhook was lost.
    # minute=20/40 stay clear of the PhonePe 15/30/45 stagger.
    "razorpay-collect-due-beat": {
        "task": "razorpay-collect-due",
        "schedule": crontab(minute=20),
    },
    "razorpay-reconcile-beat": {
        "task": "razorpay-reconcile",
        "schedule": crontab(minute=40),
    },

    # Every 6 hours (staggered)
    "phonepe-advance-payment-dates-beat": {
        "task": "phonepe-advance-payment-dates",
        "schedule": crontab(hour="*/6", minute=0),
    },
    "phonepe-ensure-scheduled-transactions-beat": {
        "task": "phonepe-ensure-scheduled-transactions",
        "schedule": crontab(hour="*/6", minute=15),
    },
    "phonepe-sync-total-payments-beat": {
        "task": "phonepe-sync-total-payments",
        "schedule": crontab(hour="*/6", minute=30),
    },
    "phonepe-archive-failed-subscriptions-beat": {
        "task": "phonepe-archive-failed-subscriptions",
        "schedule": crontab(hour="*/6", minute=45),
    },
    # minute=50 keeps the existing 0/15/30/45 stagger intact
    "phonepe-revoke-duplicate-subscriptions-beat": {
        "task": "phonepe-revoke-duplicate-subscriptions",
        "schedule": crontab(hour="*/6", minute=50),
    },
    # Picks up deliveries claimed but never sent (broker outage, worker killed
    # mid-task) — the uniqueness constraint means no later observer re-claims
    # them, so without this they would sit PENDING forever — then prunes the
    # delivered backlog. minute=55 continues the stagger.
    "autorev-webhook-maintenance-beat": {
        "task": "autorev-webhook-maintenance",
        "schedule": crontab(hour="*/6", minute=55),
    },

    # Once a day. 15:35 UTC is 21:05 IST — just ahead of the 21:31 IST non-peak
    # window, so a mandate un-paused during the day is ACTIVE with a next_payment_date
    # before that evening's redemption pass rather than waiting another 24 hours.
    # minute=35 stays clear of the hourly 15/30/45 stagger above.
    "phonepe-sync-paused-state-beat": {
        "task": "phonepe-sync-paused-state",
        "schedule": crontab(hour=15, minute=35),
    },
}

celery_app.conf.timezone = "UTC"

# docker exec autorev-workers-worker-1   celery -A phone_worker.celery_app call phonepe-revoke-duplicate-subscriptions