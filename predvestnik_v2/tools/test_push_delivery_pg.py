#!/usr/bin/env python3
"""Real PostgreSQL proof: Smart Pulse cannot lose a DM before Telegram accepts it."""
from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import push


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await push.ensure_table(db)
    transaction = connection.transaction()
    await transaction.start()
    try:
        user_id = 960000000031
        await db.execute("INSERT INTO users(user_tg_id) VALUES (?)", (user_id,))
        await push.enqueue(db, user_id, "bid_outbid_final", 10, {"title": "A"})
        await push.enqueue(db, user_id, "bid_outbid_final", 9, {"title": "B"})
        event = (await push.pending_for_user(db, user_id))[0]
        assert await push.lease_event(db, event_id=event["id"], user_id=user_id, token="a")
        assert not await push.lease_event(db, event_id=event["id"], user_id=user_id, token="b")
        assert await push.release_transient_failure(db, event_id=event["id"], user_id=user_id, token="a")
        assert await push.lease_event(db, event_id=event["id"], user_id=user_id, token="b")
        assert await push.mark_delivery_succeeded(db, event_id=event["id"], user_id=user_id, token="b")
        async with db.execute(
            "SELECT COUNT(*) FILTER (WHERE sent), COUNT(*) FILTER (WHERE delivered_at IS NOT NULL) "
            "FROM push_queue WHERE user_id=?", (user_id,)
        ) as cursor:
            sent, delivered = await cursor.fetchone()
        assert (int(sent), int(delivered)) == (2, 1)

        await push.enqueue(db, user_id, "bid_outbid_final", 8, {})
        await push.enqueue(db, user_id, "bid_outbid_final", 7, {})
        second = (await push.pending_for_user(db, user_id))[0]
        assert await push.lease_event(db, event_id=second["id"], user_id=user_id, token="blocked")
        assert await push.mark_permanent_failure(db, user_id=user_id, token="blocked", reason="forbidden") == 2
        async with db.execute(
            "SELECT COUNT(*) FILTER (WHERE sent), COUNT(*) FILTER (WHERE permanent_failure='forbidden') "
            "FROM push_queue WHERE user_id=?", (user_id,),
        ) as cursor:
            closed, classified = await cursor.fetchone()
        assert (int(closed), int(classified)) == (4, 2)
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("Smart Pulse delivery: real PostgreSQL lease/retry/permanent-failure proof OK")
