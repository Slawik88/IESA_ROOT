#!/usr/bin/env python3
"""Real PostgreSQL proof (audit A04): /api/ready means the app can serve.

- before startup marks completion -> 503, even though the schema exists;
- after completion with every required table present -> 200;
- a required table missing -> 503; /api/health stays 200 throughout.
Only a loopback DSN is accepted; startup's idempotent CREATE ... IF NOT EXISTS runs.
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
os.environ.setdefault("BOT_TOKEN", "1:readiness-test")

import httpx

from FastAPI.main import app
from infrastructure import readiness


async def status(client: httpx.AsyncClient, path: str) -> int:
    return (await client.get(path)).status_code


async def main() -> None:
    transport = httpx.ASGITransport(app=app)   # lifespan is not run, like the co-hosted bot
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert not readiness.startup_complete()
        assert await status(client, "/api/ready") == 503, "schema exists but startup has not finished"
        assert await status(client, "/api/health") == 200

        # The real startup path (bot and local stand) marks completion as its last step.
        from bot.startup_schema import ensure_runtime_schema
        from infrastructure.database import create_pool, get_pool
        await create_pool()
        await ensure_runtime_schema(get_pool())
        assert readiness.startup_complete()
        assert await status(client, "/api/ready") == 200, "startup done and all required tables present"

        original = readiness.REQUIRED_TABLES
        readiness.REQUIRED_TABLES = original + ("a04_required_table_absent",)
        try:
            assert await status(client, "/api/ready") == 503, "missing required table must fail readiness"
            assert await status(client, "/api/health") == 200, "liveness is independent"
        finally:
            readiness.REQUIRED_TABLES = original
        assert await status(client, "/api/ready") == 200


asyncio.run(main())
print("readiness: real PostgreSQL proof OK")
