#!/usr/bin/env python3
"""Prepare a disposable loopback PostgreSQL for the release gate (audit A14).

Runs exactly the production startup schema path (init_db -> ensure_chat_schema ->
ensure_runtime_schema), then the reviewed operator migrations the test suite
depends on. Production never runs this file: operator migrations stay manual
there. Loopback DSN only; idempotent, so it can run before every gate.
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
os.environ.setdefault("BOT_TOKEN", "123456:offline-bootstrap")

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.family_wallet_v1 import install_family_wallet_schema
from infrastructure.repositories.marriage_integrity import install_membership_registry

# Reviewed operator migrations, applied in this order on test databases only.
OPERATOR_MIGRATIONS = (
    ("marriage_members_v1", install_membership_registry),
    ("family_wallet_v1", install_family_wallet_schema),
)


async def table_exists(connection, name: str) -> bool:
    return await connection.fetchval("SELECT to_regclass($1) IS NOT NULL", f"predvestnik.{name}")


async def main() -> None:
    from infrastructure.database import create_pool
    from bot.core.database import init_db
    from bot.chat.schema import ensure_chat_schema
    from bot.startup_schema import ensure_runtime_schema

    pool = await create_pool()
    await init_db()
    await ensure_chat_schema()
    await ensure_runtime_schema(pool)

    connection = await asyncpg.connect(args.dsn, server_settings={"search_path": "predvestnik,public"})
    try:
        for label, install in OPERATOR_MIGRATIONS:
            async with connection.transaction():
                await install(PGAdapter(connection))
            print(f"operator migration applied: {label}")
    finally:
        await connection.close()
    await pool.close()


asyncio.run(main())
print("test database bootstrap: OK")
