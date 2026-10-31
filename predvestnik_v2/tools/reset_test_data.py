#!/usr/bin/env python3
"""Give each gate test clean game data without losing the bootstrap's reference rows.

The all-tests gate runs every proof against one shared database. Tests seed their
own users and rows, but several families (bot_admin, chat, coin, member_tags) share
the same id ranges with plain INSERTs, so whichever ran first broke the rest. A plain
TRUNCATE of everything fixes them but also wipes the reference rows the bootstrap
seeded (flags, catalogs), which broke another group of tests.

So the runner snapshots the freshly bootstrapped rows once (``--snapshot-refresh``:
every table that holds data is copied into the ``reset_backup`` schema), and before
every test this script truncates all tables and puts those rows back, with every
sequence advanced past the restored ids.

    python tools/reset_test_data.py --dsn ... --snapshot-refresh   # once, after bootstrap
    python tools/reset_test_data.py --dsn ...                      # before each test
"""
from __future__ import annotations

import argparse
import asyncio
import os
from urllib.parse import urlparse

parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True)
parser.add_argument("--snapshot-refresh", action="store_true",
                    help="re-copy the reference rows FROM the current (just bootstrapped) database")
args = parser.parse_args()
if urlparse(args.dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("only a loopback PostgreSQL DSN is allowed")
os.environ["DATABASE_URL"] = args.dsn
os.environ.setdefault("BOT_TOKEN", "123456:offline-reset")

SCHEMA = "predvestnik"
BACKUP = "reset_backup"


async def main() -> None:
    import asyncpg

    connection = await asyncpg.connect(args.dsn)
    try:
        if args.snapshot_refresh:
            await connection.execute(f'DROP SCHEMA IF EXISTS {BACKUP} CASCADE')
            await connection.execute(f'CREATE SCHEMA {BACKUP}')
            rows = await connection.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = $1 AND table_type = 'BASE TABLE'", SCHEMA)
            for row in rows:
                table = row["table_name"]
                count = await connection.fetchval(f'SELECT count(*) FROM {SCHEMA}."{table}"')
                if count:
                    await connection.execute(
                        f'CREATE TABLE {BACKUP}."{table}" AS SELECT * FROM {SCHEMA}."{table}"')
            return

        tables = [r["table_name"] for r in await connection.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = $1 AND table_type = 'BASE TABLE'", SCHEMA)]
        if tables:
            names = ", ".join(f'{SCHEMA}."{t}"' for t in tables)
            await connection.execute(f'TRUNCATE {names} RESTART IDENTITY CASCADE')
            restored = [r["table_name"] for r in await connection.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = $1 AND table_type = 'BASE TABLE'", BACKUP)]
            for table in restored:
                await connection.execute(
                    f'INSERT INTO {SCHEMA}."{table}" SELECT * FROM {BACKUP}."{table}"')
            # RESTART IDENTITY rewound every sequence; push each one past the restored rows.
            sequences = await connection.fetch(
                "SELECT sequencename FROM pg_sequences WHERE schemaname = $1", SCHEMA)
            for row in sequences:
                sequence = row["sequencename"]
                owner = await connection.fetchrow(
                    "SELECT dep_tab.relname AS table_name, attr.attname AS column_name "
                    "FROM pg_catalog.pg_class seq "
                    "JOIN pg_catalog.pg_namespace nsn ON nsn.oid = seq.relnamespace "
                    "JOIN pg_catalog.pg_depend dep ON dep.objid = seq.oid AND dep.deptype = 'a' "
                    "JOIN pg_catalog.pg_class dep_tab ON dep_tab.oid = dep.refobjid "
                    "JOIN pg_catalog.pg_attribute attr "
                    "ON attr.attrelid = dep.refobjid AND attr.attnum = dep.refobjsubid "
                    "WHERE nsn.nspname = $1 AND seq.relname = $2", SCHEMA, sequence)
                if owner is None:
                    continue
                peak = await connection.fetchval(
                    f'SELECT max("{owner["column_name"]}") FROM {SCHEMA}."{owner["table_name"]}"')
                await connection.execute(
                    f"SELECT setval('{SCHEMA}.\"{sequence}\"', GREATEST(COALESCE($1, 1), 1))", peak or 1)
    finally:
        await connection.close()


asyncio.run(main())
