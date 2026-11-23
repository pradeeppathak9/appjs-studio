"""creative serve | worker | health | db upgrade | users ... | tokens create | providers | generate"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import getpass
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path

from creative.config import Settings
from creative.logging import configure_logging


def _settings() -> Settings:
    s = Settings()
    configure_logging(s.log_level, s.log_prompts)
    return s


def cmd_serve(args) -> None:
    import uvicorn

    s = _settings()
    uvicorn.run(
        "creative.main:create_app",
        factory=True,
        host=args.host or s.host,
        port=args.port or s.port,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
        log_config=None,
    )


def cmd_worker(args) -> None:
    from creative.main import build_state, close_state, make_worker

    s = _settings()

    async def run():
        state = await build_state(s)
        worker = make_worker(state)
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop.set)
        await worker.start()
        await stop.wait()
        await worker.stop()
        await close_state(state)

    asyncio.run(run())


def cmd_health(args) -> None:
    """Exit 0 if a worker process on this host has a fresh heartbeat."""
    from sqlalchemy import text

    from creative.db.engine import create_engine

    s = Settings()

    async def check() -> bool:
        engine = create_engine(s)
        try:
            async with engine.connect() as conn:
                age = await conn.scalar(
                    text(
                        "SELECT min(extract(epoch FROM now() - heartbeat_at)) "
                        "FROM workers WHERE hostname = :h"
                    ),
                    {"h": socket.gethostname()},
                )
            return age is not None and age < s.worker_heartbeat_s * 3
        finally:
            await engine.dispose()

    sys.exit(0 if asyncio.run(check()) else 1)


def cmd_db_upgrade(args) -> None:
    from alembic import command

    from creative.db.engine import alembic_config

    s = _settings()
    command.upgrade(alembic_config(s.sqlalchemy_url), "head")
    print("database is at head")


def _password(prompt: str, given: str | None) -> str:
    if given:
        return given
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip("\n")
    first = getpass.getpass(prompt)
    if getpass.getpass("Repeat: ") != first:
        sys.exit("passwords differ")
    return first


async def _auth():
    from creative.auth.service import AuthService
    from creative.db.engine import create_engine, require_head, session_factory

    s = _settings()
    engine = create_engine(s)
    await require_head(engine)
    return AuthService(s, session_factory(engine)), engine


def cmd_create_admin(args) -> None:
    password = _password("Password for the admin: ", args.password)

    async def run():
        svc, engine = await _auth()
        try:
            user = await svc.create_first_admin(args.email, args.name, password, allow_existing=True)
            print(f"admin {user.email} created")
        finally:
            await engine.dispose()

    asyncio.run(run())


def cmd_reset_password(args) -> None:
    password = _password(f"New password for {args.email}: ", args.password)

    async def run():
        svc, engine = await _auth()
        try:
            await svc.set_password(args.email, password)
            print(f"password for {args.email} set; their sessions were ended")
        finally:
            await engine.dispose()

    asyncio.run(run())


def cmd_create_token(args) -> None:
    from sqlalchemy import select

    from creative.db.tables import User

    async def run():
        svc, engine = await _auth()
        try:
            async with svc.db() as s:
                user = await s.scalar(select(User).where(User.email == args.email.lower()))
            if user is None:
                sys.exit(f"no user {args.email}")
            _, raw = await svc.create_token(user.id, args.name)
            print(raw)
        finally:
            await engine.dispose()

    asyncio.run(run())


def _client(args):
    import httpx

    token = args.token or os.environ.get("CREATIVE_TOKEN")
    if not token:
        sys.exit("set CREATIVE_TOKEN (create one in Account, or `creative tokens create`)")
    return httpx.Client(base_url=args.url, headers={"Authorization": f"Bearer {token}"}, timeout=60)


def cmd_providers(args) -> None:
    with _client(args) as c:
        r = c.get("/v1/providers")
        r.raise_for_status()
        print(json.dumps(r.json(), indent=2))


def cmd_generate(args) -> None:
    with _client(args) as c:
        if args.template:
            files, opened = {}, []
            for spec in args.image or []:
                slot, _, path = spec.partition("=")
                f = open(path, "rb")  # noqa: SIM115
                opened.append(f)
                files[slot] = (Path(path).name, f)
            data = {}
            if args.var:
                data["variables"] = json.dumps(dict(v.split("=", 1) for v in args.var))
            if args.model:
                data["model"] = args.model
            r = c.post(f"/v1/apps/{args.app}/templates/{args.template}/generations", files=files, data=data)
            for f in opened:
                f.close()
        else:
            body = {"prompt": args.prompt, "media_type": args.media, "n": args.n, "aspect_ratio": args.aspect}
            for key in ("provider", "model"):
                if getattr(args, key):
                    body[key] = getattr(args, key)
            if args.duration:
                body["duration_seconds"] = args.duration
            r = c.post(f"/v1/apps/{args.app}/generations", json=body)
        if r.status_code >= 400:
            sys.exit(f"{r.status_code}: {r.text}")
        job = r.json()
        print(f"job {job['id']} {job['status']}")
        while job["status"] in ("queued", "running"):
            time.sleep(2)
            job = c.get(f"/v1/generations/{job['id']}").json()
            print(f"  {job['status']} (attempt {job['attempt']})")
        if job["status"] != "succeeded":
            sys.exit(f"failed: {job['error']}")
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for a in job["assets"]:
            ext = a["mime_type"].split("/")[-1].replace("jpeg", "jpg")
            dest = out / f"{job['id']}-{a['id']}.{ext}"
            dest.write_bytes(c.get(a["url"]).content)
            print(f"saved {dest}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="creative")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the API")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.set_defaults(fn=cmd_serve)
    sub.add_parser("worker", help="run the generation worker").set_defaults(fn=cmd_worker)
    sub.add_parser("health", help="worker healthcheck").set_defaults(fn=cmd_health)

    db = sub.add_parser("db").add_subparsers(dest="db_cmd", required=True)
    db.add_parser("upgrade", help="alembic upgrade head").set_defaults(fn=cmd_db_upgrade)

    u = sub.add_parser("users").add_subparsers(dest="users_cmd", required=True)
    ca = u.add_parser("create-admin", help="create an admin (first-run or recovery)")
    ca.add_argument("--email", required=True)
    ca.add_argument("--name", required=True)
    ca.add_argument("--password", help="prompted when omitted")
    ca.set_defaults(fn=cmd_create_admin)
    rp = u.add_parser("reset-password", help="set a user's password and reactivate them")
    rp.add_argument("--email", required=True)
    rp.add_argument("--password", help="prompted when omitted")
    rp.set_defaults(fn=cmd_reset_password)

    t = sub.add_parser("tokens").add_subparsers(dest="tokens_cmd", required=True)
    tc = t.add_parser("create", help="create an API token for a user and print it")
    tc.add_argument("--email", required=True)
    tc.add_argument("--name", default="cli")
    tc.set_defaults(fn=cmd_create_token)

    for name, fn in (("providers", cmd_providers), ("generate", cmd_generate)):
        c = sub.add_parser(name)
        c.add_argument("--url", default=os.environ.get("CREATIVE_URL", "http://localhost:8010"))
        c.add_argument("--token")
        c.set_defaults(fn=fn)
        if name == "generate":
            c.add_argument("--app", required=True, help="app id (see GET /v1/apps)")
            c.add_argument("prompt", nargs="?", default="")
            c.add_argument("--media", default="image", choices=["image", "video"])
            c.add_argument("--provider")
            c.add_argument("--model")
            c.add_argument("--n", type=int, default=1)
            c.add_argument("--aspect", default="1:1")
            c.add_argument("--duration", type=int)
            c.add_argument("--template", help="template id or slug")
            c.add_argument("--image", action="append", help="slot=path (repeatable)")
            c.add_argument("--var", action="append", help="name=value (repeatable)")
            c.add_argument("--out", default="./out")

    args = p.parse_args(argv)
    with contextlib.suppress(KeyboardInterrupt):
        args.fn(args)


if __name__ == "__main__":
    main()
