#!/usr/bin/env python3
"""Real PostgreSQL proof for one-shot local-rank approvals."""
from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import rank_requests


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await rank_requests.ensure_table(db)
    transaction = connection.transaction()
    await transaction.start()
    try:
        token = await rank_requests.create(
            db, chat_id=-960001, initiator_id=96001, target_id=96002,
            target_rank_before=1, new_rank_id=2,
        )
        assert await rank_requests.get_open(db, token=token, chat_id=-960001)
        assert not await rank_requests.get_open(db, token=token, chat_id=-960002)
        first = await rank_requests.consume(db, token=token, chat_id=-960001, approved_by=96003)
        assert first and int(first["approved_by"]) == 96003
        assert await rank_requests.consume(db, token=token, chat_id=-960001, approved_by=96004) is None
        assert await rank_requests.get_open(db, token=token, chat_id=-960001) is None
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("Rank requests: real PostgreSQL one-shot/wrong-chat proof OK")
