# autorev

Subscription billing and recurring-payment orchestration for PhonePe and Razorpay.

## Setup

Copy `.env.example` to `.env` and fill in the real values — `.env` is gitignored.

```bash
cp .env.example .env
(cd ../infra && docker compose up -d)             # Postgres, Redis (shared)
docker compose up -d                              # backend, frontend
docker compose -f docker-compose.worker.yaml up -d  # celery worker, beat, flower
```

### First admin

On an empty database the backend opens first-run setup (same as AppJs Studio). Open the console's
`/setup` page (http://localhost:3000/setup), enter the setup token and create the admin; you are
signed in straight away and setup closes for good.

The token is `AUTOREV_SETUP_TOKEN` from `.env`; if that is unset, one is generated, shared across
the backend's workers through Redis, and printed in the log:

```bash
docker compose logs backend | grep "setup token"
```

Remove `AUTOREV_SETUP_TOKEN` from `.env` once the admin exists. That first admin is the primary
account: it can't be demoted, renamed or deleted. Add more users from **Admin → Users**.

Account credentials are not kept in this repo.
