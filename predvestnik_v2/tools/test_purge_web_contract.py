"""Permission outages, cheap retries and fresh bot protection at the web boundary."""
import asyncio
import os
import pathlib
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "123456:local-test")
os.environ.setdefault("DATABASE_URL", "postgresql://local-test/local-test")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import httpx
from fastapi import FastAPI
from FastAPI.deps import get_db, require_tg_user
from FastAPI.routers import purge_v1 as web
from services import purge


async def run():
    app = FastAPI()
    app.include_router(web.router)
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[require_tg_user] = lambda: {"id": 101}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        with patch.object(web.bridge, "authorize_shared", AsyncMock(side_effect=purge.PurgeUnavailable("Telegram недоступен"))):
            assert (await client.get("/purge-v1/chats/-1")).status_code == 503
        with patch.object(web.bridge, "authorize_shared", AsyncMock(side_effect=purge.PurgeConflict("Нет права"))):
            assert (await client.get("/purge-v1/chats/-1")).status_code == 403
        with patch.object(web.bridge, "authorize_shared", AsyncMock()), patch.object(web.flow, "existing_start", AsyncMock(return_value={"session_id":9,"created":False,"active":True})), patch.object(web.bridge, "find_violators", AsyncMock(side_effect=AssertionError("Retry must not rebuild targets"))):
            response = await client.post("/purge-v1/chats/-1/start", json={"norm":100,"date_from":"2026-10-01","date_to":"2026-10-07","action_id":"same"})
            assert response.status_code == 200 and response.json()["session_id"] == 9, response.text
        assert (await client.post("/purge-v1/chats/-1/decision", json={"session_id":0,"user_id":1,"action":"ban","action_id":"x"})).status_code == 422
    from bot.chat import purge as bridge
    bot = SimpleNamespace(me=AsyncMock(return_value=SimpleNamespace(id=999)))
    candidates = [SimpleNamespace(user_id=uid) for uid in (999,777000,201,202)]
    with patch.object(bridge.chat_bots, "known", AsyncMock(return_value={201})), patch.object(bridge.chat_bots, "screen", AsyncMock(side_effect=AssertionError("Web preparation cannot wait for per-player Telegram calls"))):
        remaining, skipped = await bridge.screen_violators(bot, object(), -1, candidates, live=False)
        assert [v.user_id for v in remaining] == [202] and skipped == 3
    print("PASS: temporary outage503, revoked access403, cheap start retry, invalid payload, fast known-bot screening")


if __name__ == "__main__":
    asyncio.run(run())
