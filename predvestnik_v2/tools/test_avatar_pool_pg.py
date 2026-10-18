#!/usr/bin/env python3
"""Real PostgreSQL proof (audit A13): a slow Telegram avatar download holds no DB slot.

With a 2-connection pool, six concurrent /profile/avatar requests whose Telegram
download hangs must leave the pool free for other requests, share one download,
answer within the time budget, and still reject a deleted account.
Only a loopback DSN is accepted.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True)
args = parser.parse_args()
if urlparse(args.dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("only a loopback PostgreSQL DSN is allowed")
os.environ["DATABASE_URL"] = args.dsn
os.environ["DB_POOL_MAX_SIZE"] = "2"
os.environ.setdefault("BOT_TOKEN", "1:avatar-test")

import httpx

from FastAPI.deps import require_tg_user_base
from FastAPI.main import app
from FastAPI.routers import profile
from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import public_profiles_v1

USER_ID = 940_000_000_000 + int(time.time()) % 100_000
DELETED_ID = USER_ID + 1
calls = 0


async def hanging_telegram(user_id: int) -> str | None:
    global calls
    calls += 1
    await asyncio.sleep(30)
    return "data:image/jpeg;base64,AAAA"


async def always_vip(db, user_id: int) -> bool:
    return True


async def main() -> None:
    await create_pool()
    async with get_pool().acquire() as conn:
        await conn.execute("INSERT INTO users (user_tg_id) VALUES ($1), ($2)", USER_ID, DELETED_ID)
        await conn.execute("UPDATE users SET deleted_at = NOW() WHERE user_tg_id = $1", DELETED_ID)
        ref = await public_profiles_v1.ensure_reference(PGAdapter(conn), user_id=USER_ID)
        deleted_ref = await public_profiles_v1.ensure_reference(PGAdapter(conn), user_id=DELETED_ID)
    profile._fetch_tg_avatar = hanging_telegram
    profile.is_vip_active = always_vip
    profile._AVATAR_BUDGET_SEC = 1.0
    current = {"id": USER_ID}
    app.dependency_overrides[require_tg_user_base] = lambda: dict(current)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=20) as client:
            started = time.monotonic()
            requests = [asyncio.create_task(client.get("/profile/avatar")) for _ in range(6)]
            await asyncio.sleep(0.3)
            async with asyncio.timeout(1.0):   # pool of 2 is still free while 6 downloads hang
                async with get_pool().acquire() as a, get_pool().acquire() as b:
                    assert await a.fetchval("SELECT 1") == 1 and await b.fetchval("SELECT 1") == 1
            responses = await asyncio.gather(*requests)
            elapsed = time.monotonic() - started
            assert all(r.status_code == 200 and r.json() == {"avatar": None, "vip": True} for r in responses), \
                [r.text for r in responses]
            assert elapsed < 5, f"budget not applied: {elapsed:.1f}s"
            assert calls == 1, f"downloads not shared: {calls}"

            profile._AVATAR_CACHE[USER_ID] = ("data:image/jpeg;base64,AAAA", time.time())
            public = await client.get("/profile/avatar", params={"profile_ref": ref})
            assert public.json() == {"avatar": "data:image/jpeg;base64,AAAA", "vip": True}
            assert (await client.get("/profile/avatar", params={"profile_ref": "invalid"})).status_code == 404
            assert (await client.get("/profile/avatar", params={"profile_ref": deleted_ref})).status_code == 403
            async def no_vip(db, user_id):
                return False
            profile.is_vip_active = no_vip
            assert (await client.get("/profile/avatar", params={"profile_ref": ref})).json() == {"avatar": None, "vip": False}

            current["id"] = DELETED_ID
            denied = await client.get("/profile/avatar")
            assert denied.status_code == 403 and "ACCOUNT_DELETED" in denied.text, denied.text
    finally:
        app.dependency_overrides.clear()
        for task in list(profile._AVATAR_INFLIGHT.values()):
            task.cancel()
        async with get_pool().acquire() as conn:
            await conn.execute("DELETE FROM public_profile_v1_refs WHERE user_id = ANY($1::bigint[])", [USER_ID, DELETED_ID])
            await conn.execute("DELETE FROM users WHERE user_tg_id = ANY($1::bigint[])", [USER_ID, DELETED_ID])


asyncio.run(main())
print("avatar pool isolation: real PostgreSQL proof OK")
