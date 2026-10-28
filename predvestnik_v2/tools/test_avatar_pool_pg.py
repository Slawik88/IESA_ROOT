#!/usr/bin/env python3
"""Real PostgreSQL proof for player photos (audit A13, roadmap S02).

1. A slow Telegram holds no DB slot: with a 2-connection pool, six concurrent /profile/avatar requests whose
   Telegram lookup hangs leave the pool free, share one lookup and answer within the time budget.
2. A photo survives a restart: after the in-process state is dropped, the photo is served from the
   avatar_photos table without asking Telegram.
3. VIP rule: the direct address /profile/avatar/{ref} returns 404 for a non-VIP (checked on every request);
   a deleted account is refused. The admin panel still gets every player's photo, VIP or not.
4. The table schema is idempotent (a second ensure_tables changes nothing).
Only a loopback DSN is accepted.
"""
from __future__ import annotations

import argparse
import asyncio
from io import BytesIO
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
os.environ["DB_POOL_MAX_SIZE"] = "4"   # process total: 2 pooled + 2 direct (lock, LISTEN)
os.environ.setdefault("BOT_TOKEN", "1:avatar-test")

import httpx
from PIL import Image

from FastAPI.deps import require_tg_user_base
from FastAPI.main import app
from FastAPI.routers import profile
from infrastructure import telegram_photo
from infrastructure.database import create_pool, get_pool
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import avatar_photos as repo
from infrastructure.repositories import public_profiles_v1
from services import admin_avatars, avatar_photos

USER_ID = 940_000_000_000 + int(time.time()) % 100_000
DELETED_ID = USER_ID + 1
PLAIN_ID = USER_ID + 2      # not a VIP
buffer = BytesIO()
Image.new("RGB", (320, 320), "teal").save(buffer, format="JPEG")
JPEG = buffer.getvalue()
calls = {"lookup": 0, "download": 0}
vip_ids = {USER_ID, DELETED_ID}


async def hanging_lookup(user_id: int):
    calls["lookup"] += 1
    await asyncio.sleep(30)


async def found_lookup(user_id: int):
    calls["lookup"] += 1
    return telegram_photo.PhotoRef(version=f"uniq-{user_id}", file_id=f"file-{user_id}")


async def download(file_id: str) -> bytes:
    calls["download"] += 1
    return JPEG


async def vip_check(db, user_id: int) -> bool:
    return int(user_id) in vip_ids


def forget_process_state() -> None:
    """What a deploy does to memory: in-flight tasks, failure pauses and the schema flag are gone."""
    for task in list(avatar_photos._inflight.values()):
        task.cancel()
    avatar_photos._inflight.clear()
    avatar_photos._failed_at.clear()
    repo._ready = False


async def main() -> None:
    await create_pool()
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await conn.execute("INSERT INTO users (user_tg_id) VALUES ($1), ($2), ($3)", USER_ID, DELETED_ID, PLAIN_ID)
        await conn.execute("UPDATE users SET deleted_at = NOW() WHERE user_tg_id = $1", DELETED_ID)
        ref = await public_profiles_v1.ensure_reference(db, user_id=USER_ID)
        deleted_ref = await public_profiles_v1.ensure_reference(db, user_id=DELETED_ID)
        plain_ref = await public_profiles_v1.ensure_reference(db, user_id=PLAIN_ID)
        await repo.ensure_tables(db)
        repo._ready = False
        await repo.ensure_tables(db)   # idempotent: a second run on an existing table changes nothing
        await conn.execute("DELETE FROM avatar_photos WHERE user_id = ANY($1::bigint[])", [USER_ID, DELETED_ID, PLAIN_ID])
    profile.is_vip_active = vip_check
    telegram_photo.download_file = download
    current = {"id": USER_ID}
    app.dependency_overrides[require_tg_user_base] = lambda: dict(current)
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test", timeout=20) as client:
            # 1. A hanging Telegram: pool stays free, one shared lookup, answers within the budget.
            telegram_photo.current_photo = hanging_lookup
            avatar_photos.BUDGET_SEC = 1.0
            started = time.monotonic()
            requests = [asyncio.create_task(client.get("/profile/avatar")) for _ in range(6)]
            await asyncio.sleep(0.3)
            async with asyncio.timeout(1.0):
                async with get_pool().acquire() as a, get_pool().acquire() as b:
                    assert await a.fetchval("SELECT 1") == 1 and await b.fetchval("SELECT 1") == 1
            responses = await asyncio.gather(*requests)
            elapsed = time.monotonic() - started
            # "loading", not "absent": the photo is still expected once Telegram answers again.
            assert all(r.status_code == 200 and r.json() == {"avatar": None, "vip": True, "avatar_state": "loading"} for r in responses), \
                [r.text for r in responses]
            assert elapsed < 5, f"budget not applied: {elapsed:.1f}s"
            assert calls["lookup"] == 1, f"lookups not shared: {calls}"

            # Telegram is back: the photo is fetched once and stored.
            forget_process_state()
            telegram_photo.current_photo = found_lookup
            body = (await client.get("/profile/avatar")).json()
            assert body["avatar_state"] == "ready" and body["avatar"].startswith(f"/profile/avatar/{ref}?v="), body
            assert calls["download"] == 1

            # 2. After a "deploy" the photo comes from PostgreSQL, Telegram is not asked.
            forget_process_state()
            lookups = calls["lookup"]
            me_like = (await client.get(f"/profile/avatar?profile_ref={ref}")).json()
            assert me_like == body | {"vip": True}, me_like
            image = await client.get(body["avatar"])
            assert image.status_code == 200 and image.headers["content-type"] == "image/webp"
            assert calls["lookup"] == lookups and calls["download"] == 1, f"Telegram asked after restart: {calls}"
            assert (await client.get(body["avatar"], headers={"if-none-match": image.headers["etag"]})).status_code == 304

            # 3. VIP rule on the direct address, every request; deleted account refused.
            vip_ids.discard(USER_ID)
            assert (await client.get(body["avatar"])).status_code == 404, "a lapsed VIP's photo leaked by URL"
            assert (await client.get(f"/profile/avatar?profile_ref={ref}")).json() == {"avatar": None, "vip": False, "avatar_state": "vip_only"}
            vip_ids.add(USER_ID)
            assert (await client.get(f"/profile/avatar?profile_ref={deleted_ref}")).status_code == 403
            assert (await client.get(f"/profile/avatar/{deleted_ref}")).status_code == 404
            assert (await client.get("/profile/avatar", params={"profile_ref": "invalid"})).status_code == 404

            # Admin panel: every player's photo, VIP or not — through the signed admin link.
            assert (await client.get(f"/profile/avatar/{plain_ref}")).status_code == 404
            plain_photo = await admin_avatars.bytes_for(PLAIN_ID)
            assert plain_photo and plain_photo[8:12] == b"WEBP", "the admin panel must see a non-VIP photo"
            admin = await client.get(admin_avatars.avatar_url(PLAIN_ID))
            assert admin.status_code == 200 and admin.headers["content-type"] == "image/webp"

            current["id"] = DELETED_ID
            denied = await client.get("/profile/avatar")
            assert denied.status_code == 403 and "ACCOUNT_DELETED" in denied.text, denied.text
    finally:
        app.dependency_overrides.clear()
        forget_process_state()
        async with get_pool().acquire() as conn:
            ids = [USER_ID, DELETED_ID, PLAIN_ID]
            await conn.execute("DELETE FROM avatar_photos WHERE user_id = ANY($1::bigint[])", ids)
            await conn.execute("DELETE FROM public_profile_v1_refs WHERE user_id = ANY($1::bigint[])", ids)
            await conn.execute("DELETE FROM users WHERE user_tg_id = ANY($1::bigint[])", ids)


asyncio.run(main())
print("avatar photos: pool isolation, survives restart, VIP on the direct address, admin sees all, idempotent schema — real PostgreSQL OK")
