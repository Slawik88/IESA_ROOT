"""Разовая проверка онбординга «Тропы»: колонка, чтение, запись, идемпотентность.

Запускается на loopback-БД после bootstrap_test_db; всё внутри транзакции с откатом.
"""
from __future__ import annotations

import argparse, asyncio, pathlib, sys
from urllib.parse import urlparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import users as repo
from services import pets_v2 as service


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    tx = conn.transaction()
    await tx.start()
    try:
        user = 770000001
        await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user,))
        assert await repo.get_trail_intro_done(db, user) is False, "fresh user must not be marked"
        view = await service.overview(db, user)
        assert view["intro_done"] is False, "/me must expose intro_done=false first"
        assert await service.mark_intro_done(db, user) is True
        assert await service.mark_intro_done(db, user) is True, "repeat mark stays idempotent"
        assert await repo.get_trail_intro_done(db, user) is True, "flag must persist"
        view = await service.overview(db, user)
        assert view["intro_done"] is True, "/me must expose intro_done=true after mark"
        print("OK: trail intro flag read/mark/idempotent verified")
    finally:
        await tx.rollback()
        await conn.close()


if __name__ == "__main__":
    import asyncpg

    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True, type=local_dsn)
    asyncio.run(run(parser.parse_args().dsn))
