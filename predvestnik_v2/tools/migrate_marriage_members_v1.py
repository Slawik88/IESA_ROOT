#!/usr/bin/env python3
"""Operator-controlled migration for the global marriage-members registry.

The command is loopback-only and requires ``--apply``.  It does no automatic
historical repair: any readiness blocker aborts the transaction.
"""
from __future__ import annotations

import argparse
import asyncio
from urllib.parse import urlparse

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.marriage_integrity import install_membership_registry


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction():
            await install_membership_registry(PGAdapter(connection))
    finally:
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
parser.add_argument("--apply", action="store_true", help="perform the reviewed migration")
args = parser.parse_args()
if not args.apply:
    raise SystemExit("refusing to migrate without --apply")
asyncio.run(run(args.dsn))
print("marriage members v1: migration applied")
