#!/usr/bin/env python3
"""HTTP surface of the League demo: the page and its assets load, the API is closed without early access.

Run: PYTHONPATH=. python3 tools/test_league_v1_asgi.py --dsn postgresql://postgres@127.0.0.1:55432/league_test
(after tools/test_league_v1_pg.py has created the test users).
"""
from __future__ import annotations

import argparse
import asyncio
import os

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused@127.0.0.1/unused")

import asyncpg  # noqa: E402
import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402

from FastAPI import deps  # noqa: E402
from FastAPI.routers import league_v1 as router_module  # noqa: E402
from infrastructure.pg_adapter import PGAdapter  # noqa: E402

TESTER, PLAYER = 910_001, 910_002


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    # The gate below needs the tester's role and its grant row. Seed them here too:
    # in the all-tests gate this file runs before its *_pg sibling (alphabetical),
    # so relying on the sibling's users made this proof fail every full run.
    from core import league_v1 as league_rules
    from services import admin_access
    await admin_access.ensure_schema(db)
    await db.execute("INSERT INTO users (user_tg_id, user_tg_username, bot_rank) VALUES (?, 'tester', 1), (?, 'player', 0) "
                     "ON CONFLICT (user_tg_id) DO UPDATE SET bot_rank = EXCLUDED.bot_rank", (TESTER, PLAYER))
    await db.execute("INSERT INTO admin_role_grants (key, min_rank, updated_by) VALUES (?, 1, 1) "
                     "ON CONFLICT (key) DO UPDATE SET min_rank = 1", (league_rules.FLAG_KEY,))
    who = {"id": PLAYER}
    app = FastAPI()
    app.include_router(router_module.router)

    async def fake_db():
        yield db

    async def fake_user():
        return dict(who)

    app.dependency_overrides[deps.get_db] = fake_db
    app.dependency_overrides[deps.require_tg_user] = fake_user
    from core import league_pass as pass_rules
    from services import league_v1 as league
    public = {"on": False}   # the test fixes the clock: first before season 2, then after it
    router_module.league_rules.is_public = lambda now: public["on"]
    pass_rules.active = lambda now: public["on"]
    league._season = lambda now=None: "s2" if public["on"] else "demo-1"
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            for path in ("/league", "/league-demo"):
                page = await client.get(path)
                assert page.status_code == 200 and "<title>Рейтинг" in page.text and "{{" not in page.text, path
            for name in router_module._ASSETS:
                assert (await client.get(f"/static/league-demo/{name}")).status_code == 200, name
                if name != "casual-games-v3.css":   # the look of the casual pages only (Rhythm, Minesweeper): the League page does not load it
                    assert f"/static/league-demo/{name}?v=" in page.text, f"{name} is served but not linked from the page"
            assert (await client.get("/static/league-demo/secret.py")).status_code == 404
            assert (await client.get("/league-demo/api/access")).json() == {"allowed": False, "public": False}
            state = (await client.get("/league-demo/api/pass")).json()
            assert state["active"] is False and state["starts_at"].startswith("2026-10-25"), state
            refused = await client.post("/league-demo/api/pass/claim", json={"season": 2})
            assert refused.status_code == 409, "nothing to claim before season 2"
            for method, path, body in (("GET", "/league-demo/api/me", None), ("POST", "/league-demo/api/runs", {"game": "rhythm", "level": 1}),
                                       ("POST", "/league-demo/api/reset", {})):
                response = await client.request(method, path, json=body)
                assert response.status_code == 403, (path, response.status_code)
            who["id"] = TESTER
            assert (await client.get("/league-demo/api/access")).json() == {"allowed": True, "public": False}
            me = await client.get("/league-demo/api/me")
            assert me.status_code == 200 and me.json()["demo"] is True
            bad = await client.post("/league-demo/api/runs", json={"game": "minesweeper", "level": 5})
            assert bad.status_code == 409 and "предыдущий" in bad.json()["detail"]
            public["on"] = True
            who["id"] = PLAYER
            assert (await client.get("/league-demo/api/access")).json() == {"allowed": True, "public": True}
            me = await client.get("/league-demo/api/me")
            assert me.status_code == 200 and me.json()["demo"] is False, "from season 2 every player plays the League"
            assert (await client.post("/league-demo/api/reset", json={})).status_code == 409, "a real season cannot be reset"
            assert (await client.get("/league-demo/api/pass/casual/casino/x")).status_code == 422, "only the two casual games"
            line = await client.get("/league-demo/api/pass/casual/rhythm/never-played")
            assert line.status_code == 200 and line.json()["counted"] is False, line.text
    finally:
        # Remove this run's grant row: the *_pg sibling inserts its own with a plain
        # INSERT (it would collide) and its gate expects no row beforehand.
        await db.execute("DELETE FROM admin_role_grants WHERE key = ?", (league_rules.FLAG_KEY,))
        await connection.close()
    print("PASS league HTTP: page and assets; before season 2 early access only (403), after it open to all")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(run(parser.parse_args().dsn))
