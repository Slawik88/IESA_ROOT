"""Real PostgreSQL + HMAC auth: safe reports, duplicate ACKs, quotas and staff gates."""
import argparse
import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import time
from urllib.parse import urlparse
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


async def main(dsn):
    os.environ["DATABASE_URL"] = dsn
    os.environ["DB_POOL_MAX_SIZE"] = "6"   # process total: 4 pooled + 2 direct (lock, LISTEN)
    os.environ.setdefault("BOT_TOKEN","123456:offline-support-test")
    from FastAPI import deps, support_middleware
    from FastAPI.auth import create_session_token
    from FastAPI.routers import support
    from FastAPI.routers.bot_admin import auth, diagnostics
    from infrastructure.database import create_pool,get_pool
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import support_reports as repo
    from services import admin_people, presence_v1, support_reports
    from services.support_diagnostics import recent

    users = [941001001,941001002,941001004,941001005,941001006]
    actor,other,junior,developer,ordinary = users
    await create_pool()
    async with get_pool().acquire() as connection:
        db = PGAdapter(connection)
        await repo.ensure_tables(db)
        await admin_people.ensure_schema(db)
        for uid in users:
            await db.execute("INSERT INTO users(user_tg_id,user_tg_name) VALUES (?,'QA Support') ON CONFLICT(user_tg_id) DO NOTHING",(uid,))
    app = FastAPI()
    app.state.asset_version = "qa-release"
    app.include_router(support.router)
    app.include_router(diagnostics.router)
    app.middleware("http")(support_middleware.record_request)
    def headers(uid):
        return {"x-session-token":create_session_token(uid)}
    async def rank(db,uid):
        return {developer:5,junior:4}.get(uid,0)
    def body():
        now = int(time.time()*1000)
        return {"expected_user_id":str(actor),"client_report_id":str(uuid4()),"captured_at":now,"category":"avatar","comment":"VIP, фото нет <script>",
                "include_diagnostics":True,"environment":{"telegram_platform":"android","model":"QA Phone","tg_photo_available":True,
                    "initData":"NEVER_SAVE","user_agent":"Mozilla token=VERY_SECRET"},
                "events":[{"at":now,"kind":"avatar","data":{"vip":True,"has_avatar":False,"body":"PRIVATE_CHAT"}},
                          {"at":now,"kind":"request","data":{"route":"/profile/u/Cannibal_Lecturer?initData=NEVER_SAVE","request_id":str(uuid4()),"status":200,"authorization":"NEVER_SAVE"}},
                          {"at":now-3600001,"kind":"request","data":{"status":500}}]}
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(deps,"_capture_signals",AsyncMock()))
            stack.enter_context(patch.object(presence_v1,"note_activity",AsyncMock()))
            stack.enter_context(patch.object(auth,"get_bot_rank",rank))
            stack.enter_context(patch.object(auth.admin_security,"revoked_before",AsyncMock(return_value=None)))
            stack.enter_context(patch.object(auth.admin_access,"load_grants",AsyncMock(return_value={"section:diagnostics":1})))
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://test") as client:
                assert (await client.post("/support/reports",json=body())).status_code == 401
                # Slow uploads must not occupy any pooled database connection.
                gate=asyncio.Event()
                async def stream(encoded):
                    yield encoded[:10]
                    await gate.wait()
                    yield encoded[10:]
                uploads=[asyncio.create_task(client.post("/support/reports",content=stream(json.dumps({**body(),"expected_user_id":str(ordinary)}).encode()),headers=headers(ordinary))) for _ in range(4)]
                await asyncio.sleep(.2)
                async with asyncio.timeout(2):
                    async with get_pool().acquire() as a,get_pool().acquire() as b,get_pool().acquire() as c,get_pool().acquire() as d:
                        assert await a.fetchval("SELECT 1")==1 and await d.fetchval("SELECT 1")==1
                gate.set()
                assert all(r.status_code==200 for r in await asyncio.gather(*uploads))
                recent.record(actor,"avatar",{"source":"botapi","stage":"photos","outcome":"empty"})
                recent.record(other,"avatar",{"source":"cache","stage":"privateOtherUser","outcome":"photo"})
                payload = body()
                first = await client.post("/support/reports",json=payload,headers=headers(actor))
                assert first.status_code == 200,first.text
                receipt = first.json(); rid = receipt["id"]
                repeated = await asyncio.gather(*(client.post("/support/reports",json=payload,headers=headers(actor)) for _ in range(2)))
                assert all(r.status_code==200 and r.json()["id"]==rid and r.json()["replayed"] for r in repeated)
                for uid in (ordinary,junior):
                    for suffix in ("",f"/{rid}",f"/{rid}/download"):
                        assert (await client.get("/bot-admin/api/diagnostics"+suffix,headers=headers(uid))).status_code == 403
                    assert (await client.post(f"/bot-admin/api/diagnostics/{rid}/status",json={"status":"resolved"},headers=headers(uid))).status_code == 403
                assert (await client.get(f"/bot-admin/api/diagnostics/{rid}")).status_code == 401
                result = await client.get(f"/bot-admin/api/diagnostics/{rid}/download",headers=headers(developer))
                assert result.status_code == 200 and "attachment" in result.headers["content-disposition"]
                report = result.json()
                assert report["user_id"] == actor and len(report["payload"]["events"]) == 2
                encoded = json.dumps(report)
                assert all(secret not in encoded for secret in ("NEVER_SAVE","VERY_SECRET","PRIVATE_CHAT","Cannibal_Lecturer","privateOtherUser")),encoded
                assert report["server_context"]["app_version"] == "qa-release"
                assert report["server_context"]["diagnostics"]["events"][0]["data"]["outcome"] == "empty"
                # Same client ID is scoped by authenticated author, never another account.
                # Expired Telegram A + valid browser B must not relabel A's report.
                mismatched={**headers(other),"x-init-data":"expired-user-A"}
                assert (await client.post("/support/reports",json=payload,headers=mismatched)).status_code == 409
                peer = await client.post("/support/reports",json={**payload,"expected_user_id":str(other)},headers=headers(other))
                assert peer.status_code==200 and peer.json()["id"] != rid
                for _ in range(5):
                    assert (await client.post("/support/reports",json=body(),headers=headers(actor))).status_code == 200
                assert (await client.post("/support/reports",json=body(),headers=headers(actor))).status_code == 429
                assert (await client.post("/support/reports",json=payload,headers=headers(actor))).json()["id"] == rid
                assert (await client.post("/support/reports",json={**payload,"comment":"changed"},headers=headers(actor))).status_code == 400
                assert (await client.post("/support/reports",content=b'x'*(1024*1024+1),headers=headers(other))).status_code == 413
                assert (await client.post("/support/reports",json={**body(),"category":[],"expected_user_id":str(other)},headers=headers(other))).status_code == 400
                no_diagnostics = {**body(),"include_diagnostics":False,"expected_user_id":str(other)}
                plain = (await client.post("/support/reports",json=no_diagnostics,headers=headers(other))).json()
                plain_report = (await client.get(f'/bot-admin/api/diagnostics/{plain["id"]}',headers=headers(developer))).json()
                assert plain_report["payload"]["events"] == [] and plain_report["payload"]["environment"] == {} and plain_report["server_context"] == {}
                status_result = await client.post(f"/bot-admin/api/diagnostics/{rid}/status",json={"status":"resolved"},headers=headers(developer))
                assert status_result.status_code == 200,status_result.text
                filtered = (await client.get("/bot-admin/api/diagnostics?status=resolved&category=avatar",headers=headers(developer))).json()
                assert len(filtered["items"])==1 and filtered["items"][0]["id"]==rid
                async with get_pool().acquire() as connection:
                    assert await connection.fetchval("SELECT COUNT(*) FROM bot_admin_actions WHERE actor_id=$1 AND action='support_report_status'",developer) == 1
                    await connection.execute("UPDATE support_reports SET created_at=CLOCK_TIMESTAMP()-INTERVAL '31 days' WHERE id=$1::uuid",rid)
                    await repo.cleanup(PGAdapter(connection))
                    assert not await repo.get(PGAdapter(connection),rid)
        print("PASS real PG/API: signed auth, silent avatar report, sanitized hour, same-author context, concurrent duplicate receipts, quota retry, body limit, private export, fixed rank5 gate, status audit and retention")
    finally:
        async with get_pool().acquire() as connection:
            await connection.execute("DELETE FROM support_reports WHERE user_id=ANY($1::bigint[])",users)
            await connection.execute("DELETE FROM bot_admin_actions WHERE actor_id=ANY($1::bigint[])",users)
            await connection.execute("DELETE FROM users WHERE user_tg_id=ANY($1::bigint[])",users)
        await get_pool().close()


if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--dsn",required=True);args=parser.parse_args()
    if urlparse(args.dsn).hostname not in {"localhost","127.0.0.1","::1"}:
        raise SystemExit("loopback PostgreSQL required")
    asyncio.run(main(args.dsn))
