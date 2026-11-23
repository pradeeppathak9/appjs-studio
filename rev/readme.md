# autorev

Subscription billing and recurring-payment orchestration for PhonePe and Razorpay.

## Setup

Copy `.env.example` to `.env` and fill in the real values — `.env` is gitignored.

```bash
cp .env.example .env
(cd ../infra && docker compose up -d)             # Postgres, Redis, RabbitMQ (shared)
docker compose up -d                              # backend, frontend
docker compose -f docker-compose.worker.yaml up -d  # celery worker, beat, flower
```

Account credentials are not kept in this repo.
