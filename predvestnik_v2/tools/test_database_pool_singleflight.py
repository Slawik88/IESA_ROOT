"""Concurrent readiness/startup calls must create exactly one small DB pool."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infrastructure import database


async def run() -> None:
    original_pool = database._pool
    original_create = database.asyncpg.create_pool
    original_diagnose = database._diagnose
    original_tcp = database._tcp_test
    original_preprod = database.is_preprod
    old_url = os.environ.get("DATABASE_URL")
    old_max = os.environ.get("DB_POOL_MAX_SIZE")
    calls: list[dict] = []
    sentinel = object()

    async def fake_create_pool(*args, **kwargs):
        calls.append(kwargs)
        await asyncio.sleep(0.02)
        return sentinel

    async def no_diagnose(*args, **kwargs):
        return None

    async def tcp_ok(*args, **kwargs):
        return "OK"

    try:
        database._pool = None
        database._pool_create_lock = asyncio.Lock()
        database.asyncpg.create_pool = fake_create_pool
        database._diagnose = no_diagnose
        database._tcp_test = tcp_ok
        database.is_preprod = lambda: False
        os.environ["DATABASE_URL"] = "postgresql://contract@127.0.0.1:5432/contract"
        os.environ.pop("PREDVESTNIK_DATABASE_URL", None)
        os.environ["DB_POOL_MAX_SIZE"] = "99"

        pools = await asyncio.gather(*(database.create_pool() for _ in range(25)))
        assert all(pool is sentinel for pool in pools)
        assert len(calls) == 1, "concurrent startup created more than one pool"
        assert calls[0]["min_size"] == 1 and calls[0]["max_size"] == 10
        os.environ["DB_POOL_MAX_SIZE"] = "invalid"
        assert database._pool_max_size() == 5
    finally:
        database._pool = original_pool
        database.asyncpg.create_pool = original_create
        database._diagnose = original_diagnose
        database._tcp_test = original_tcp
        database.is_preprod = original_preprod
        if old_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = old_url
        if old_max is None:
            os.environ.pop("DB_POOL_MAX_SIZE", None)
        else:
            os.environ["DB_POOL_MAX_SIZE"] = old_max

    print("OK: concurrent startup creates one bounded PostgreSQL pool")


if __name__ == "__main__":
    asyncio.run(run())
