#!/usr/bin/env python3
"""Real PostgreSQL rollback proof for family-wallet opening-balance migration."""
from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.family_wallet_v1 import install_family_wallet_schema


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    transaction = connection.transaction()
    await transaction.start()
    try:
        db = PGAdapter(connection)
        async with db.execute(
            "INSERT INTO marriages (chat_id, user1_id, user1_name, user2_id, user2_name, "
            "family_balance, family_balance_diamonds, family_balance_dark_mora, family_balance_zarniki) "
            "VALUES (?, ?, 'wallet-a', ?, 'wallet-b', ?, ?, ?, ?) RETURNING id",
            (-930001, 930000000001, 930000000002, 7.5, 3.25, 1, 12),
        ) as cursor:
            marriage_id = int((await cursor.fetchone())[0])
        await install_family_wallet_schema(db)
        async with db.execute(
            "SELECT mora, diamonds, dark_mora, zarniki FROM family_wallet_balances WHERE marriage_id = ?",
            (marriage_id,),
        ) as cursor:
            row = await cursor.fetchone()
        assert tuple(str(value) for value in row) == ("7.500000", "3.250000", "1.000000", "12.000000")
        async with db.execute(
            "SELECT COUNT(*) FROM family_wallet_ledger WHERE marriage_id = ?", (marriage_id,)
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 4
        async with db.execute(
            "SELECT metadata_json->>'provenance' FROM family_wallet_operations "
            "WHERE marriage_id = ?", (marriage_id,)
        ) as cursor:
            assert (await cursor.fetchone())[0] == "legacy_unattributed"
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("family wallet schema: real PostgreSQL rollback proof OK")
