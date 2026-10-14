#!/usr/bin/env python3
"""Real PostgreSQL proof (audit A06): /ws/{user_id} applies the HTTP gameplay gates.

- valid account connects; foreign ID, deleted account and a preprod non-allowlisted
  account are rejected before accept; DB failure fails closed (1011);
- an open session is closed with 1008 once the account stops being allowed.
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
os.environ.setdefault("BOT_TOKEN", "1:ws-gates-test")
os.environ.pop("PREDVESTNIK_ENV", None)

import asyncpg
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from FastAPI import main as main_module
from FastAPI import notifications
from FastAPI.auth import create_session_token
from FastAPI.main import app
from infrastructure import database

ACTIVE = 950_000_000_000 + int(time.time()) % 100_000
DELETED = ACTIVE + 1


async def no_listener() -> bool:
    return False


def fresh_pool() -> None:
    # TestClient runs every WebSocket on its own event loop; an asyncpg pool is
    # bound to the loop that created it, so let the endpoint create a new one.
    database._pool = None


def rejected_code(client: TestClient, path: str) -> int:
    fresh_pool()
    try:
        with client.websocket_connect(path) as ws:
            ws.receive_json()
    except WebSocketDisconnect as exc:
        return exc.code
    raise AssertionError(f"{path} was accepted")


async def seed(sql: str, *params) -> None:
    conn = await asyncpg.connect(args.dsn, server_settings={"search_path": "predvestnik,public"})
    try:
        await conn.execute(sql, *params)
    finally:
        await conn.close()


class FakeSocket:
    def __init__(self) -> None:
        self.closed_code = None

    async def send_json(self, event: dict) -> None:
        pass

    async def receive_text(self) -> str:
        await asyncio.Future()

    async def close(self, code: int = 1000) -> None:
        self.closed_code = code


async def watchdog_closes_revoked_session() -> None:
    allowed = {"value": True}

    async def still_allowed() -> bool:
        return allowed["value"]

    socket = FakeSocket()
    task = asyncio.create_task(notifications.ws_session(
        socket, ACTIVE, still_allowed=still_allowed, recheck_sec=0.05))
    await asyncio.sleep(0.2)
    assert not task.done(), "allowed session must stay open"
    allowed["value"] = False
    await asyncio.wait_for(task, 2)
    assert socket.closed_code == 1008, socket.closed_code
    assert ACTIVE not in notifications._queues


def main() -> None:
    asyncio.run(seed("INSERT INTO users (user_tg_id) VALUES ($1), ($2)", ACTIVE, DELETED))
    asyncio.run(seed("UPDATE users SET deleted_at = NOW() WHERE user_tg_id = $1", DELETED))
    notifications.ensure_balance_listener = no_listener
    try:
        client = TestClient(app)   # lifespan not run, like the co-hosted bot
        fresh_pool()
        with client.websocket_connect(f"/ws/{ACTIVE}?token={create_session_token(ACTIVE)}") as ws:
            assert ws.receive_json()["type"] == "app_version"

        assert rejected_code(client, f"/ws/{ACTIVE}?token={create_session_token(DELETED)}") == 1008, "foreign id"
        assert rejected_code(client, f"/ws/{DELETED}?token={create_session_token(DELETED)}") == 1008, "deleted"

        os.environ["PREDVESTNIK_ENV"] = "preprod"
        os.environ["PREPROD_ALLOWED_TG_IDS"] = str(DELETED)
        try:
            assert rejected_code(client, f"/ws/{ACTIVE}?token={create_session_token(ACTIVE)}") == 1008, "preprod"
        finally:
            os.environ.pop("PREDVESTNIK_ENV", None)
            os.environ.pop("PREPROD_ALLOWED_TG_IDS", None)

        original = main_module.create_pool

        async def broken_pool():
            raise OSError("database unavailable")

        main_module.create_pool = broken_pool
        try:
            assert rejected_code(client, f"/ws/{ACTIVE}?token={create_session_token(ACTIVE)}") == 1011, "fail closed"
        finally:
            main_module.create_pool = original

        asyncio.run(watchdog_closes_revoked_session())
    finally:
        asyncio.run(seed("DELETE FROM users WHERE user_tg_id = ANY($1::bigint[])", [ACTIVE, DELETED]))


main()
print("ws account gates: real PostgreSQL proof OK")
