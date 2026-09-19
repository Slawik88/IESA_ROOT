#!/usr/bin/env python3
"""Rollback proof for owner-bound admin-chat bind requests on loopback Postgres."""

import argparse
import asyncio
import os
from urllib.parse import urlparse
from uuid import uuid4

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories.routing import (
    BindRequestError,
    consume_bind_request,
    create_bind_request,
)


def loopback_dsn(value: str) -> str:
    if urlparse(value).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only loopback PostgreSQL is allowed")
    return value


async def expect_rejected(coro, reason: str) -> None:
    try:
        await coro
    except BindRequestError:
        return
    raise AssertionError(reason)


async def run(value: str) -> None:
    connection = await asyncpg.connect(value)
    transaction = connection.transaction()
    await transaction.start()
    try:
        db = PGAdapter(connection)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_bind_requests (
                nonce TEXT PRIMARY KEY,
                main_chat_id BIGINT NOT NULL,
                main_chat_title TEXT NOT NULL,
                creator_id BIGINT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS purge_sessions (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                status TEXT DEFAULT 'active'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_bind_audit (
                id BIGSERIAL PRIMARY KEY,
                main_chat_id BIGINT NOT NULL,
                previous_admin_chat_id BIGINT,
                admin_chat_id BIGINT NOT NULL,
                actor_id BIGINT NOT NULL,
                bound_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await db.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_links_admin_chat
            ON chat_links (admin_chat_id) WHERE admin_chat_id IS NOT NULL
        """)

        first_nonce = await create_bind_request(db, -101, "main", 7)
        await expect_rejected(
            consume_bind_request(db, nonce=first_nonce, creator_id=8, admin_chat_id=-202),
            "a foreign creator consumed the request",
        )
        first = await consume_bind_request(
            db, nonce=first_nonce, creator_id=7, admin_chat_id=-202
        )
        assert first.main_chat_id == -101
        async with db.execute(
            "SELECT previous_admin_chat_id, admin_chat_id, actor_id "
            "FROM chat_bind_audit WHERE main_chat_id = ?",
            (-101,),
        ) as cursor:
            audit_row = await cursor.fetchone()
        assert audit_row == (None, -202, 7)
        await expect_rejected(
            consume_bind_request(db, nonce=first_nonce, creator_id=7, admin_chat_id=-203),
            "a replay created a second binding",
        )

        second_nonce = await create_bind_request(db, -102, "other", 7)
        await expect_rejected(
            consume_bind_request(db, nonce=second_nonce, creator_id=7, admin_chat_id=-202),
            "one admin destination was bound to two source chats",
        )

        await db.execute(
            "INSERT INTO chat_bind_requests (nonce, main_chat_id, main_chat_title, creator_id, expires_at) "
            "VALUES (?, ?, ?, ?, NOW() - INTERVAL '1 second')",
            ("expired-bind-request", -103, "expired", 7),
        )
        await expect_rejected(
            consume_bind_request(
                db, nonce="expired-bind-request", creator_id=7, admin_chat_id=-203
            ),
            "an expired request was accepted",
        )

        await db.execute(
            "INSERT INTO purge_sessions (chat_id, initiator_id, norm, status) "
            "VALUES (?, ?, ?, 'active')",
            (-101, 7, 1),
        )
        rebind_nonce = await create_bind_request(db, -101, "main", 7)
        await expect_rejected(
            consume_bind_request(db, nonce=rebind_nonce, creator_id=7, admin_chat_id=-204),
            "an active purge was silently rerouted",
        )
    finally:
        await transaction.rollback()
        await connection.close()


async def run_concurrent_redemption_proof(value: str) -> None:
    """Two callback deliveries may bind once, but never consume twice."""
    source_chat_id = -(800_000_000_000 + (uuid4().int % 100_000_000_000))
    first_destination = source_chat_id - 1
    second_destination = source_chat_id - 2
    owner_id = 7
    admin = await asyncpg.connect(value)
    try:
        await admin.execute("""
            CREATE TABLE IF NOT EXISTS chat_bind_requests (
                nonce TEXT PRIMARY KEY,
                main_chat_id BIGINT NOT NULL,
                main_chat_title TEXT NOT NULL,
                creator_id BIGINT NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await admin.execute("""
            CREATE TABLE IF NOT EXISTS chat_bind_audit (
                id BIGSERIAL PRIMARY KEY,
                main_chat_id BIGINT NOT NULL,
                previous_admin_chat_id BIGINT,
                admin_chat_id BIGINT NOT NULL,
                actor_id BIGINT NOT NULL,
                bound_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await admin.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_links_admin_chat
            ON chat_links (admin_chat_id) WHERE admin_chat_id IS NOT NULL
        """)
        db = PGAdapter(admin)
        nonce = await create_bind_request(db, source_chat_id, "race", owner_id)

        async def deliver_once(destination: int):
            connection = await asyncpg.connect(value)
            try:
                return await consume_bind_request(
                    PGAdapter(connection),
                    nonce=nonce,
                    creator_id=owner_id,
                    admin_chat_id=destination,
                )
            except BindRequestError:
                return None
            finally:
                await connection.close()

        first, second = await asyncio.gather(
            deliver_once(first_destination), deliver_once(second_destination)
        )
        assert sum(item is not None for item in (first, second)) == 1
        async with db.execute(
            "SELECT admin_chat_id FROM chat_links WHERE main_chat_id = ?",
            (source_chat_id,),
        ) as cursor:
            route = await cursor.fetchone()
        assert route and int(route[0]) in {first_destination, second_destination}
        async with db.execute(
            "SELECT COUNT(*) FROM chat_bind_requests WHERE nonce = ?",
            (nonce,),
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 0
    finally:
        # Exact disposable rows only; no player or production-route data is touched.
        await admin.execute("DELETE FROM chat_bind_requests WHERE main_chat_id = $1", source_chat_id)
        await admin.execute("DELETE FROM chat_bind_audit WHERE main_chat_id = $1", source_chat_id)
        await admin.execute("DELETE FROM chat_links WHERE main_chat_id = $1", source_chat_id)
        await admin.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", type=loopback_dsn, default=os.getenv("DATABASE_URL"))
arguments = parser.parse_args()
if not arguments.dsn:
    parser.error("--dsn or DATABASE_URL is required")
asyncio.run(run(arguments.dsn))
asyncio.run(run_concurrent_redemption_proof(arguments.dsn))
print("admin bind repository: rollback proof OK")
