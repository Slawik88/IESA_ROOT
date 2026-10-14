#!/usr/bin/env python3
"""Prepare a disposable loopback PostgreSQL for the release gate (audit A14).

Runs exactly the production startup schema path (bot: init_db -> ensure_chat_schema
-> ensure_runtime_schema; web: the FastAPI lifespan ensure list). The chat
schema step already installs the family registry and wallet (bot/chat/family.py),
so no operator migration is applied separately. Loopback DSN only; idempotent,
so it can run before every gate.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True)
args = parser.parse_args()
if urlparse(args.dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("only a loopback PostgreSQL DSN is allowed")
os.environ["DATABASE_URL"] = args.dsn
# create_pool falls back to this outside preprod; never let it reach a real DB.
os.environ.pop("PREDVESTNIK_DATABASE_URL", None)
os.environ.setdefault("BOT_TOKEN", "123456:offline-bootstrap")


async def main() -> None:
    from infrastructure.database import create_pool
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema
    from bot.startup_schema import ensure_runtime_schema

    pool = await create_pool()
    await init_db()
    await ensure_chat_schema()
    await ensure_runtime_schema(pool)
    # Production co-hosts the web app; its lifespan creates the module tables
    # (quests, chests, pets, mafia, ...). Only the schema part is wanted here:
    # the background loops would otherwise take one step during shutdown.
    import FastAPI.main as web

    async def _idle() -> None:
        return None

    web._run_skins_v3_migration = web._run_broadcast_scheduler = web._run_owner_digest = _idle
    async with web.lifespan(web.app):
        pass
    await pool.close()


asyncio.run(main())
print("test database bootstrap: OK")
