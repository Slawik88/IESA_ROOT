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
    who = {"id": PLAYER}
    app = FastAPI()
    app.include_router(router_module.router)

    async def fake_db():
        yield db

    async def fake_user():
        return dict(who)

    app.dependency_overrides[deps.get_db] = fake_db
    app.dependency_overrides[deps.require_tg_user] = fake_user
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            page = await client.get("/league-demo")
            assert page.status_code == 200 and "Лига сезона" in page.text and "{{" not in page.text
            for name in ("league-demo.css", "league-demo.js", "league-mines.js", "league-rhythm.js"):
                assert (await client.get(f"/static/league-demo/{name}")).status_code == 200, name
            assert (await client.get("/static/league-demo/secret.py")).status_code == 404
            assert (await client.get("/league-demo/api/access")).json() == {"allowed": False}
            for method, path, body in (("GET", "/league-demo/api/me", None), ("POST", "/league-demo/api/runs", {"game": "rhythm", "level": 1}),
                                       ("POST", "/league-demo/api/reset", {})):
                response = await client.request(method, path, json=body)
                assert response.status_code == 403, (path, response.status_code)
            who["id"] = TESTER
            assert (await client.get("/league-demo/api/access")).json() == {"allowed": True}
            me = await client.get("/league-demo/api/me")
            assert me.status_code == 200 and me.json()["demo"] is True
            bad = await client.post("/league-demo/api/runs", json={"game": "minesweeper", "level": 5})
            assert bad.status_code == 409 and "предыдущий" in bad.json()["detail"]
    finally:
        await connection.close()
    print("PASS league demo HTTP: page and assets, 403 without early access, 409 for a locked level")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(run(parser.parse_args().dsn))
