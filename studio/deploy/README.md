# Deploying AppJs Studio

Three images, built on your machine and pushed to a registry; the server only pulls and runs them.

| Image | From | Runs |
|---|---|---|
| `appjs-studio-api` | `studio/Dockerfile` | `migrate` (once per start), `api`, `worker` |
| `appjs-studio-web` | `studio/web/Dockerfile` | the console (nginx), which also proxies `/v1` to the API |
| `restyle-web` | `restyle-web/Dockerfile` | the Restyle web app (nginx), which proxies only `/v1/app` to the API |

The server runs [`../../infra`](../../infra) first (shared Postgres, Redis, RabbitMQ, and Caddy for
HTTPS on `STUDIO_DOMAIN` and `RESTYLE_DOMAIN`), then [`docker-compose.prod.yaml`](docker-compose.prod.yaml)
(Studio's api, worker and console, and the Restyle web app), which joins infra's `appjs` network. Only
ports 80 and 443 are open.

## 1. Build and publish (your machine)

Uses GitHub Container Registry (`ghcr.io`). Log in once with a GitHub token that has `write:packages`
(github.com → Settings → Developer settings → Personal access tokens):

```bash
echo "$GHCR_TOKEN" | docker login ghcr.io -u pradeeppathak9 --password-stdin
```

Build for the server's CPU (`linux/amd64` for most VPSes; `linux/arm64` for ARM ones) and push. On an
Apple-silicon Mac the platform flag matters: without it the image is arm64 and won't start on an
x86 server.

```bash
cd ~/Work/appjs/studio
TAG=$(date +%Y-%m-%d)-$(git rev-parse --short HEAD)
REG=ghcr.io/pradeeppathak9

docker buildx build --platform linux/amd64 -t $REG/appjs-studio-api:$TAG -t $REG/appjs-studio-api:latest --push .
docker buildx build --platform linux/amd64 -t $REG/appjs-studio-web:$TAG -t $REG/appjs-studio-web:latest --push web
docker buildx build --platform linux/amd64 -t $REG/restyle-web:$TAG -t $REG/restyle-web:latest --push ../restyle-web
```

New packages on ghcr.io are private: the server logs in to pull them (step 2), or make them public
under github.com → your profile → Packages → the package → Settings.

## 2. First start (the server)

Needs Docker with the compose plugin, and DNS A records for both domains pointing at the server.

```bash
git clone git@github.com:pradeeppathak9/appjs-studio.git ~/appjs   # or copy infra/ and studio/deploy/

# 1. infra: Postgres (role + schema per app), Redis, RabbitMQ, Caddy
cd ~/appjs/infra
cp .env.example .env && chmod 600 .env
nano .env           # long random passwords, APP_DB_CREATEDB=false, STUDIO_DOMAIN, RESTYLE_DOMAIN
docker compose --profile edge up -d

# 2. Studio and the Restyle web app
cd ~/appjs/studio/deploy
cp env.example .env && chmod 600 .env
nano .env           # STUDIO_DB_PASSWORD (= infra's), SECRETS_KEY, OTP_SECRET, SETUP_TOKEN, keys
mkdir -p data && sudo chown 10001:10001 data      # the image's app user writes uploads and results here

echo "$GHCR_TOKEN" | docker login ghcr.io -u pradeeppathak9 --password-stdin   # token with read:packages
docker compose -f docker-compose.prod.yaml pull
docker compose -f docker-compose.prod.yaml up -d
docker compose -f docker-compose.prod.yaml ps
```

Open `https://STUDIO_DOMAIN/setup`, enter `SETUP_TOKEN`, create the admin. Then remove `SETUP_TOKEN` from
`.env` and run `up -d` again.

Mobile apps use `https://STUDIO_DOMAIN` as their base URL (Restyle: `appjs.baseUrl` in `local.properties`):
the console's nginx forwards `/v1/app/*` to the API.

The Restyle web app is at `https://RESTYLE_DOMAIN`. Set `RESTYLE_APP_KEY` (the restyle-ai app key) in
`.env`. For "Continue with Google" there, add `https://RESTYLE_DOMAIN` to the Google OAuth Web
client's **Authorized JavaScript origins** (Google Cloud → Credentials).

## 3. Deploy a new version

On your machine: step 1 again (a new `TAG`). On the server:

```bash
cd ~/appjs/studio/deploy
docker compose -f docker-compose.prod.yaml pull
docker compose -f docker-compose.prod.yaml up -d      # migrate runs before api and worker start
```

Pin a version by setting `TAG=` in `.env` instead of `latest`; set it back to roll back. Migrations
only go forward, so rolling back across a migration needs a database restore.

## Operate

```bash
docker compose -f docker-compose.prod.yaml logs -f api worker        # logs
docker compose -f docker-compose.prod.yaml exec api studio users reset-password --email you@example.com
docker compose -f docker-compose.prod.yaml up -d --scale worker=3   # more workers

# backup: the database and ./data (uploads, inputs, generated images) go together
(cd ~/appjs/infra && docker compose exec -T postgres pg_dump -U postgres -n studio appjs) | gzip > db-$(date +%F).sql.gz
tar czf data-$(date +%F).tgz data
```

Keep `SECRETS_KEY` and `OTP_SECRET` stable: a new `SECRETS_KEY` makes every saved credential (apps'
MSG91 and provider keys) unreadable.
