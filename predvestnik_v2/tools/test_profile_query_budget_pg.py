"""Measure the steady-state SQL budget of GET /profile/me on loopback PostgreSQL."""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import os
import sys

parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True)
parser.add_argument("--max-queries", type=int, default=None)
args = parser.parse_args()
if "127.0.0.1" not in args.dsn and "localhost" not in args.dsn:
    raise SystemExit("Only a loopback PostgreSQL DSN is allowed")

os.environ["DATABASE_URL"] = args.dsn
os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DEVELOPER_ID", "990000099")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


async def main() -> None:
    import httpx
    from FastAPI.auth import create_session_token
    import FastAPI.main as web
    from bot.core.database import init_db
    from infrastructure.database import create_pool, get_pool
    from infrastructure.pg_adapter import PGAdapter

    await create_pool()
    await init_db()
    user_id = 990000099
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        await db.execute(
            "INSERT INTO users (user_tg_id,user_tg_username) VALUES (?,?) ON CONFLICT DO NOTHING",
            (user_id, "profile_budget"),
        )

    active = contextvars.ContextVar("profile_query_counter", default=False)
    statements: list[str] = []
    original_execute = PGAdapter.execute

    def counted_execute(self, sql: str, values=()):
        if active.get():
            statements.append(" ".join(sql.split()))
        return original_execute(self, sql, values)

    PGAdapter.execute = counted_execute
    try:
        headers = {"x-session-token": create_session_token(user_id)}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=web.app), base_url="http://test"
        ) as client:
            # Warm one-time schema and process caches before measuring normal use.
            warm = await client.get("/profile/me", headers=headers)
            assert warm.status_code == 200, warm.text
            token = active.set(True)
            try:
                response = await client.get("/profile/me", headers=headers)
            finally:
                active.reset(token)
            assert response.status_code == 200, response.text
    finally:
        PGAdapter.execute = original_execute

    count = len(statements)
    print(f"PROFILE_ME_SQL_QUERIES={count}")
    if args.max_queries is not None:
        assert count <= args.max_queries, (count, statements)


if __name__ == "__main__":
    asyncio.run(main())
