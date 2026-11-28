"""Deploy the appjs services to a remote machine with Fabric.

Run it without installing anything into the repo (there is no root toolchain):

    uvx --from fabric fab -l                      # list tasks
    uvx --from fabric fab check                   # can we reach the server, is Docker there?
    uvx --from fabric fab bootstrap               # first time: clone the repo, create .env files
    uvx --from fabric fab deploy                  # infra + studio (autorev is off: add --with-autorev)
    uvx --from fabric fab studio --tag 2026-11-24-abc1234

Pick the server with `--target <name>` (a key of TARGETS below, default "prod"), or override it from
the environment: APPJS_HOST, APPJS_USER, APPJS_PORT, APPJS_REPO_DIR, APPJS_BRANCH. `fab -H user@host
<task>` works too.

What runs where (see each service's README):
- infra/                         Postgres, Redis, Caddy (`--profile edge`)
- studio/deploy/                 Studio api/worker/console + restyle-web, from images on ghcr.io
                                 (build and push them first with `fab build-studio`)
- autorev/                       backend + console, built from source on the server
- autorev/ (worker compose)      Celery worker, beat, flower

Secrets never pass through this file: each service's `.env` lives on the server and is edited there.
"""

from __future__ import annotations

import os
import shlex
from datetime import datetime

from fabric import Connection, task
from invoke import Context
from invoke.exceptions import Exit

# ── Servers ──────────────────────────────────────────────────────────────────────────────────
# Fill in `host` and `user` (or set APPJS_HOST / APPJS_USER). Add more entries for other machines,
# e.g. "staging", and pick one with `fab <task> --target staging`.
TARGETS: dict[str, dict] = {
    "prod": {
        "host": "143.110.178.170",
        "user": "ppathak",
        "port": 22,
        "repo_dir": "~/appjs",
        "branch": "main",
    },
}

REPO_URL = "git@github.com:pradeeppathak9/appjs-studio.git"
REGISTRY = "ghcr.io/pradeeppathak9"
PLATFORM = "linux/amd64"  # the server's CPU; linux/arm64 for ARM servers

STUDIO_COMPOSE = "docker compose -f docker-compose.prod.yaml"
AUTOREV_WORKERS_COMPOSE = "docker compose -f docker-compose.worker.yaml"

# .env files created from their examples on first setup (then edited on the server).
ENV_FILES = {
    "infra/.env": "infra/.env.example",
    "studio/deploy/.env": "studio/deploy/env.example",
    "autorev/.env": "autorev/.env.example",
}


# ── Helpers ──────────────────────────────────────────────────────────────────────────────────
def _settings(target: str) -> dict:
    if target not in TARGETS:
        raise Exit(f"Unknown target {target!r}. Known: {', '.join(TARGETS)}")
    cfg = dict(TARGETS[target])
    for key in ("host", "user", "port", "repo_dir", "branch"):
        value = os.environ.get(f"APPJS_{key.upper()}")
        if value:
            cfg[key] = value
    return cfg


def _conn(c, target: str) -> tuple[Connection, dict]:
    """The server to work on: `fab -H ...` if given, else TARGETS[target] (+ APPJS_* overrides)."""
    cfg = _settings(target)
    if isinstance(c, Connection):
        return c, cfg
    if not cfg["host"]:
        raise Exit(
            f"No host for target {target!r}: fill in TARGETS[{target!r}] in fabfile.py, "
            "set APPJS_HOST, or pass -H user@host."
        )
    conn = Connection(host=cfg["host"], user=cfg["user"] or None, port=int(cfg["port"]))
    return conn, cfg


def _repo(cfg: dict, sub: str = "") -> str:
    return f"{cfg['repo_dir'].rstrip('/')}/{sub}".rstrip("/")


def _rsync_repo(conn: Connection, cfg: dict) -> None:
    """Sync the local working copy (including .git, excluding .env/data/caches) to the server."""
    local = Context()
    user_Prefix = f"{conn.user}@" if conn.user else ""
    dest = f"{user_Prefix}{conn.host}:{_repo(cfg)}/"
    local.run(
        f"rsync -az --no-owner --no-group --delete "
        f"-e 'ssh -p {int(conn.port or 22)}' "
        "--include '.env.example' --exclude '.env' --exclude '.env.*' "
        "--exclude 'node_modules' --exclude '.venv' --exclude '__pycache__' "
        "--exclude '.pytest_cache' --exclude 'studio/data' --exclude 'studio/deploy/data' "
        "--exclude 'restyle/build' --exclude 'restyle/app/build' --exclude 'restyle/.gradle' "
        "--exclude 'backups' "
        f"./ {shlex.quote(dest)}"
    )


def _update_code(conn: Connection, cfg: dict) -> None:
    branch = shlex.quote(cfg["branch"])
    can_pull = conn.run(
        "GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new' "
        f"git -C {_repo(cfg)} ls-remote origin HEAD >/dev/null 2>&1",
        warn=True,
        hide=True,
    ).ok
    if not can_pull:
        _rsync_repo(conn, cfg)
        with conn.cd(_repo(cfg)):
            conn.run("git log -1 --oneline")
        return
    with conn.cd(_repo(cfg)):
        conn.run("git fetch --prune origin")
        conn.run(f"git checkout {branch}")
        conn.run(f"git pull --ff-only origin {branch}")
        conn.run("git log -1 --oneline")


def _require_env(conn: Connection, cfg: dict, path: str) -> None:
    if conn.run(f"test -f {_repo(cfg, path)}", warn=True, hide=True).failed:
        raise Exit(f"{path} is missing on the server. Run `fab bootstrap`, then edit it there.")


# ── Tasks: checks and first setup ────────────────────────────────────────────────────────────
@task(help={"target": "Server name from TARGETS (default: prod)"})
def check(c, target="prod"):
    """Reach the server and show Docker, Compose and disk space."""
    conn, _ = _conn(c, target)
    conn.run("hostname && uptime")
    conn.run("docker --version && docker compose version")
    conn.run("df -h / | tail -1")


@task(
    help={
        "target": "Server name from TARGETS (default: prod)",
        "sync_local": "Sync local repo over rsync when server has no GitHub deploy key (default: auto)",
    }
)
def bootstrap(c, target="prod", sync_local=None):
    """First setup: clone (or rsync) the repo, create each .env from its example, create Studio's data dir.

    The server needs Docker with the compose plugin, and read access to the GitHub repo (a deploy key)
    or local rsync fallback. Edit the created .env files on the server before the first deploy.
    """
    conn, cfg = _conn(c, target)
    repo = _repo(cfg)
    if conn.run(f"test -d {repo}/.git", warn=True, hide=True).failed:
        if sync_local is None:
            can_clone = conn.run(
                "GIT_SSH_COMMAND='ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new' "
                f"git ls-remote {REPO_URL} HEAD >/dev/null 2>&1",
                warn=True,
                hide=True,
            ).ok
            sync_local = not can_clone
        if sync_local:
            _rsync_repo(conn, cfg)
        else:
            conn.run(f"git clone --branch {shlex.quote(cfg['branch'])} {REPO_URL} {repo}")
    else:
        _update_code(conn, cfg)

    with conn.cd(repo):
        for env_file, example in ENV_FILES.items():
            created = conn.run(
                f"test -f {env_file} || (cp {example} {env_file} && chmod 600 {env_file} && echo created)",
                hide=True,
            ).stdout.strip()
            print(f"{env_file}: {'created from ' + example if created else 'already there, left alone'}")
        # The Studio image's app user (uid 10001) writes uploads and results here.
        conn.run("mkdir -p studio/deploy/data")
        conn.run("docker run --rm -v \"$PWD/studio/deploy/data:/data\" alpine chown -R 10001:10001 /data")

    print(
        "\nNext, on the server:\n"
        f"  {repo}/infra/.env          long random passwords, APP_DB_CREATEDB=false, STUDIO_DOMAIN, RESTYLE_DOMAIN\n"
        f"  {repo}/studio/deploy/.env  STUDIO_DB_PASSWORD (= infra's), SECRETS_KEY, OTP_SECRET, SETUP_TOKEN, keys\n"
        f"  {repo}/autorev/.env        AUTOREV_DATABASE_URL (password = infra's AUTOREV_DB_PASSWORD), AUTOREV_SETUP_TOKEN\n"
        "  docker login ghcr.io       (to pull Studio's private images)\n"
        "Then: fab deploy"
    )


# ── Tasks: build (your machine) ──────────────────────────────────────────────────────────────
@task(help={"tag": "Image tag (default: YYYY-MM-DD-<short sha>)", "platform": f"default {PLATFORM}"})
def build_studio(c, tag="", platform=PLATFORM):
    """Build and push Studio's api and console images and restyle-web's, tagged `tag` and `latest`."""
    local = c if isinstance(c, Context) and not isinstance(c, Connection) else Context()
    if not tag:
        sha = local.run("git rev-parse --short HEAD", hide=True).stdout.strip()
        tag = f"{datetime.now():%Y-%m-%d}-{sha}"
    images = {
        "appjs-studio-api": "studio",
        "appjs-studio-web": "studio/web",
        "restyle-web": "restyle-web",
    }
    for name, context in images.items():
        local.run(
            f"docker buildx build --platform {platform} "
            f"-t {REGISTRY}/{name}:{tag} -t {REGISTRY}/{name}:latest --push {context}",
            pty=True,
        )
    print(f"\nPushed tag {tag}. Deploy it with: fab studio --tag {tag}")


# ── Tasks: deploy (the server) ───────────────────────────────────────────────────────────────
@task(
    help={
        "target": "Server name from TARGETS (default: prod)",
        "pull": "git pull first (default: yes)",
        "edge": "Also start Caddy for HTTPS domains (default: yes if STUDIO_DOMAIN is set in infra/.env)",
    }
)
def infra(c, target="prod", pull=True, edge=None):
    """Start or update shared Postgres, Redis (and Caddy when domains are set)."""
    conn, cfg = _conn(c, target)
    if pull:
        _update_code(conn, cfg)
    _require_env(conn, cfg, "infra/.env")
    if edge is None:
        has_domain = conn.run(
            f"grep -Eq '^(APPJS_DOMAIN|STUDIO_DOMAIN|RESTYLE_DOMAIN|AUTOREV_DOMAIN|MARKTMAKRS_DOMAIN)=[^[:space:]#]+' {_repo(cfg, 'infra/.env')}",
            warn=True,
            hide=True,
        ).ok
        edge = has_domain
    profile = "--profile edge " if edge else ""
    with conn.cd(_repo(cfg, "infra")):
        conn.run(f"docker compose {profile}pull")
        conn.run(f"docker compose {profile}up -d --remove-orphans")
        if edge:
            conn.run("docker compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile")
        conn.run(f"docker compose {profile}ps")


@task(
    help={
        "target": "Server name from TARGETS (default: prod)",
        "tag": "Image tag to run (default: TAG from studio/deploy/.env, else latest)",
        "pull": "git pull first (default: yes)",
        "build": "Build images on the server instead of pulling from ghcr.io (default: no)",
    }
)
def studio(c, target="prod", tag="", pull=True, build=False):
    """Pull (or build) and restart Studio (migrate, api, worker, console) and restyle-web."""
    conn, cfg = _conn(c, target)
    if pull:
        _update_code(conn, cfg)
    _require_env(conn, cfg, "studio/deploy/.env")
    env = {"TAG": tag} if tag else {}
    if build:
        with conn.cd(_repo(cfg)):
            t = shlex.quote(tag or "latest")
            conn.run(f"docker build -t {REGISTRY}/appjs-studio-api:{t} -t {REGISTRY}/appjs-studio-api:latest studio")
            conn.run(f"docker build -t {REGISTRY}/appjs-studio-web:{t} -t {REGISTRY}/appjs-studio-web:latest studio/web")
            conn.run(f"docker build -t {REGISTRY}/restyle-web:{t} -t {REGISTRY}/restyle-web:latest restyle-web")
    with conn.cd(_repo(cfg, "studio/deploy")):
        if not build:
            conn.run(f"{STUDIO_COMPOSE} pull", env=env)
        conn.run(f"{STUDIO_COMPOSE} up -d --remove-orphans", env=env)  # migrate runs before api/worker
        conn.run(f"{STUDIO_COMPOSE} ps", env=env)


@task(
    help={
        "target": "Server name from TARGETS (default: prod)",
        "workers": "Also rebuild the Celery worker, beat and flower (default: yes)",
        "pull": "git pull first (default: yes)",
    }
)
def autorev(c, target="prod", workers=True, pull=True):
    """Build and restart autorev's backend and console (and its Celery workers)."""
    conn, cfg = _conn(c, target)
    if pull:
        _update_code(conn, cfg)
    _require_env(conn, cfg, "autorev/.env")
    with conn.cd(_repo(cfg, "autorev")):
        conn.run("docker compose up -d --build --remove-orphans")
        if workers:
            conn.run(f"{AUTOREV_WORKERS_COMPOSE} up -d --build --remove-orphans")
        conn.run("docker compose ps")
        if workers:
            conn.run(f"{AUTOREV_WORKERS_COMPOSE} ps")


@task(
    help={
        "target": "Server name from TARGETS (default: prod)",
        "tag": "Studio image tag",
        "build": "Build Studio images on the server instead of pulling from ghcr.io (default: no)",
        "with_autorev": "Also deploy autorev (default: no, it is switched off for now; see `fab autorev-stop`)",
    }
)
def deploy(c, target="prod", tag="", build=False, with_autorev=False):
    """Infra, then studio (and autorev with --with-autorev, which is off for now)."""
    conn, cfg = _conn(c, target)
    _update_code(conn, cfg)
    infra(conn, target=target, pull=False)
    studio(conn, target=target, tag=tag, pull=False, build=build)
    if with_autorev:
        autorev(conn, target=target, pull=False)
    else:
        print("Skipping autorev (switched off). Deploy it with --with-autorev or `fab autorev`.")


@task(help={"target": "Server name from TARGETS (default: prod)"})
def autorev_stop(c, target="prod"):
    """Switch autorev off: stop its backend, console and Celery workers. Data stays; `fab autorev` brings it back."""
    conn, cfg = _conn(c, target)
    with conn.cd(_repo(cfg, "autorev")):
        conn.run(f"{AUTOREV_WORKERS_COMPOSE} stop", warn=True)
        conn.run("docker compose stop", warn=True)


# ── Tasks: operate ───────────────────────────────────────────────────────────────────────────
_STACKS = {
    "infra": ("infra", "docker compose --profile edge"),
    "studio": ("studio/deploy", STUDIO_COMPOSE),
    "autorev": ("autorev", "docker compose"),
    "autorev-workers": ("autorev", AUTOREV_WORKERS_COMPOSE),
}


def _stack(name: str) -> tuple[str, str]:
    if name not in _STACKS:
        raise Exit(f"Unknown stack {name!r}. Known: {', '.join(_STACKS)}")
    return _STACKS[name]


@task(help={"target": "Server name from TARGETS (default: prod)"})
def ps(c, target="prod"):
    """Containers of every stack."""
    conn, cfg = _conn(c, target)
    for name, (path, compose) in _STACKS.items():
        print(f"\n== {name}")
        with conn.cd(_repo(cfg, path)):
            conn.run(f"{compose} ps", warn=True)


@task(
    help={
        "stack": f"One of: {', '.join(_STACKS)}",
        "service": "Service in that stack (default: all)",
        "lines": "Lines of history (default: 200)",
        "follow": "Keep following (default: no)",
        "target": "Server name from TARGETS (default: prod)",
    }
)
def logs(c, stack, service="", lines=200, follow=False, target="prod"):
    """Logs of a stack, e.g. `fab logs studio --service api --follow`."""
    conn, cfg = _conn(c, target)
    path, compose = _stack(stack)
    flags = f"--tail {int(lines)}" + (" -f" if follow else "")
    with conn.cd(_repo(cfg, path)):
        conn.run(f"{compose} logs {flags} {shlex.quote(service) if service else ''}", pty=True)


@task(
    help={
        "stack": f"One of: {', '.join(_STACKS)}",
        "service": "Service to restart (default: all in the stack)",
        "target": "Server name from TARGETS (default: prod)",
    }
)
def restart(c, stack, service="", target="prod"):
    """Restart a stack or one of its services."""
    conn, cfg = _conn(c, target)
    path, compose = _stack(stack)
    with conn.cd(_repo(cfg, path)):
        conn.run(f"{compose} restart {shlex.quote(service) if service else ''}")


@task(
    help={
        "download": "Copy the dump to ./backups on this machine (default: yes)",
        "target": "Server name from TARGETS (default: prod)",
    }
)
def backup(c, download=True, target="prod"):
    """Dump the whole `appjs` database (every app's schema) and Studio's data dir on the server."""
    conn, cfg = _conn(c, target)
    stamp = f"{datetime.now():%Y-%m-%d-%H%M%S}"
    remote_dir = _repo(cfg, "../appjs-backups")
    conn.run(f"mkdir -p {remote_dir}")
    db_file = f"{remote_dir}/appjs-{stamp}.dump"
    data_file = f"{remote_dir}/studio-data-{stamp}.tgz"
    with conn.cd(_repo(cfg, "infra")):
        conn.run(f"docker compose exec -T postgres pg_dump -U postgres -Fc appjs > {db_file}")
    conn.run(f"tar czf {data_file} -C {_repo(cfg, 'studio/deploy')} data", warn=True)
    conn.run(f"ls -lh {remote_dir} | tail -5")
    if download:
        os.makedirs("backups", exist_ok=True)
        home = conn.run("echo $HOME", hide=True).stdout.strip()
        remote_path = db_file.replace("~", home, 1)
        conn.get(remote_path, local=f"backups/{os.path.basename(remote_path)}")
        print(f"Downloaded backups/{os.path.basename(remote_path)}")
