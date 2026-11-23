from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_admin_user
from app.celery_client import celery_client
from app.models import User

router = APIRouter(prefix="/api/admin/tasks", tags=["admin-tasks"])

# Mirrors the @celery_app.task names registered in workers/phone_worker.py
AVAILABLE_TASKS = [
    "phonepe-sync-subscription-state",
    "phonepe-sync-paused-state",
    "phonepe-notify-redemption-due",
    "phonepe-sync-redemption-txn-state",
    "phonepe-sync-scheduled-transactions",
    "phonepe-advance-payment-dates",
    "phonepe-ensure-scheduled-transactions",
    "phonepe-sync-total-payments",
    "phonepe-archive-failed-subscriptions",
    "phonepe-revoke-duplicate-subscriptions",
    "autorev-webhook-maintenance",
]


@router.get("")
def list_tasks(_: User = Depends(get_current_admin_user)):
    return {"tasks": AVAILABLE_TASKS}


@router.post("/{task_name}/trigger")
def trigger_task(task_name: str, _: User = Depends(get_current_admin_user)):
    if task_name not in AVAILABLE_TASKS:
        raise HTTPException(status_code=404, detail="Unknown task")

    result = celery_client.send_task(task_name)
    return {"task_name": task_name, "task_id": result.id}
