#!/usr/bin/env python3
"""Apply the reviewed family-wallet custody schema on a loopback test DB only."""
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
    try:
        async with connection.transaction():
            await install_family_wallet_schema(PGAdapter(connection))
    finally:
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
parser.add_argument("--apply", action="store_true")
args = parser.parse_args()
if not args.apply:
    raise SystemExit("refusing to migrate without --apply")
asyncio.run(run(args.dsn))
print("family wallet v1: migration applied")
