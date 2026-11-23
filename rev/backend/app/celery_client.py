import os

from celery import Celery

from app.config import settings

# The two processes name the broker differently: the backend gets
# AUTOREV_CELERY_BROKER_URL (Settings has env_prefix="AUTOREV_"), while the
# worker image is given a bare CELERY_BROKER_URL by docker-compose.worker.yaml.
# This module is imported in both — app/webhooks.py enqueues deliveries from the
# worker as well as from request paths — so honour either, bare name first,
# rather than silently falling back to the default broker URL.
BROKER_URL = os.environ.get("CELERY_BROKER_URL") or settings.celery_broker_url

celery_client = Celery("phone_worker", broker=BROKER_URL)
