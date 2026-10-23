"""Online API auth/flag/global-ban/staff boundaries; no database or Telegram needed."""
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from fastapi import FastAPI
from FastAPI.deps import get_db, require_tg_user, require_tg_user_base
from FastAPI.routers import mafia_online as online
from FastAPI.routers.bot_admin import mafia_online as moderation
from FastAPI.routers.bot_admin.auth import staff_user
from services import admin_access


async def main():
    app = FastAPI()
    app.include_router(online.router)
    app.include_router(moderation.router)
    app.dependency_overrides[get_db] = lambda: object()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/mafia-online")).status_code == 401
        assert (await client.get("/bot-admin/api/mafia-online-reports")).status_code == 401
        person = {"id": 7654321, "first_name": "Игрок"}
        app.dependency_overrides[require_tg_user] = lambda: person
        app.dependency_overrides[require_tg_user_base] = lambda: person
        with patch("infrastructure.repositories.system_flags.is_enabled", new=AsyncMock(return_value=False)):
            assert (await client.get("/mafia-online")).status_code == 403
        with patch("infrastructure.repositories.system_flags.is_enabled", new=AsyncMock(return_value=True)), \
             patch.object(online.global_moderation, "is_blocked", new=AsyncMock(return_value=False)) as blocked, \
             patch.object(online.global_moderation, "ban_info", new=AsyncMock(return_value=None)) as banned, \
             patch.object(online.game, "hub", new=AsyncMock(return_value={"active": None, "rooms": []})), \
             patch.object(online.chat, "moderate", new=AsyncMock()) as moderate:
            assert (await client.get("/mafia-online")).status_code == 200
            blocked.return_value = True
            assert (await client.get("/mafia-online")).status_code == 403
            blocked.return_value = False
            banned.return_value = {"reason": "global ban"}
            assert (await client.post("/mafia-online/quick", json={})).status_code == 403
            banned.return_value = None
            assert (await client.post("/mafia-online/rooms/1/messages", json={"text": "x", "nonce": "bad"})).status_code == 422
            for path in ('/mafia-online/rooms/0','/mafia-online/rooms/-1','/mafia-online/rooms/9223372036854775808',
                         '/mafia-online/rooms/1?after=9223372036854775808','/mafia-online/rooms/1?before=9223372036854775808'):
                assert (await client.get(path)).status_code == 422, path
            assert (await client.post('/mafia-online/rooms/1/join',json={'invite':'я'})).status_code==422
            assert (await client.post('/mafia-online/rooms/1/moderation',json={'kind':'hide','message_id':2**63})).status_code==422
            await client.post("/mafia-online/rooms/1/moderation", json={"kind": "hide", "message_id": 7, "staff": True})
            assert "staff" not in moderate.await_args.kwargs, "HTTP payload cannot grant staff powers"
        app.dependency_overrides[staff_user] = lambda: {"id": 7, "kind": "owner", "rank": 0, "grants": {}}
        assert (await client.get("/bot-admin/api/mafia-online-reports")).status_code == 403
        app.dependency_overrides[staff_user] = lambda: admin_access.staff_principal(7, 6, {})
        with patch.object(moderation.repo, "reports", new=AsyncMock(return_value=[])):
            assert (await client.get("/bot-admin/api/mafia-online-reports")).status_code == 200
    from bot.chat.framework import registry
    assert registry.get("мафия").handler.__module__ == "bot.chat.mafia"
    assert registry.get("мафия онлайн").handler.__module__ == "bot.chat.mafia_online"
    from FastAPI.main import app as production_app
    saved = dict(production_app.dependency_overrides)
    production_app.dependency_overrides[get_db] = lambda: object()
    production_app.dependency_overrides[online.participant] = lambda: person
    production_app.dependency_overrides[online.router.dependencies[0].dependency] = lambda: None
    try:
        with patch("services.feature_switches.disabled", new=AsyncMock(return_value=None)), \
             patch.object(online.game, "hub", new=AsyncMock(return_value={"active": None, "rooms": []})):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=production_app), base_url="http://test") as client:
                assert (await client.get("/mafia-online")).status_code == 200
                assert (await client.get("/static/mafia-online-v3.css")).status_code == 200
                assert "function openMafiaOnline(" in (await client.get("/static/app.js")).text
                assert "mafia-online-v3.css" in (await client.get("/")).text
    finally:
        production_app.dependency_overrides.clear()
        production_app.dependency_overrides.update(saved)
    print("PASS authentication, separate flag, global blocks/bans, staff reports, no privilege injection, local command intact")


if __name__ == "__main__":
    asyncio.run(main())
