#!/usr/bin/env python3
"""Aggregate-only preflight for the future family-ledger migration.

This tool only accepts a loopback PostgreSQL DSN.  It cannot accidentally be
pointed at production and it performs no DDL or balance mutation.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from urllib.parse import urlparse

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.marriage_integrity import (
    audit_family_migration_readiness,
    migration_is_safe,
)


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> int:
    connection = await asyncpg.connect(dsn)
    try:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            audit = await audit_family_migration_readiness(PGAdapter(connection))
    finally:
        await connection.close()
    print(json.dumps({"safe": migration_is_safe(audit), "blockers": audit}, sort_keys=True))
    return 0 if migration_is_safe(audit) else 2


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
arguments = parser.parse_args()
raise SystemExit(asyncio.run(run(arguments.dsn)))
