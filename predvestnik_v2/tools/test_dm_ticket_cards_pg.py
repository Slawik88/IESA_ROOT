#!/usr/bin/env python3
"""Real PostgreSQL proof of the ticket card limit and the ticket list pages (S23d, core/dm_tickets.py).

Run on a loopback database (the proof works in its own throw-away schema and drops it at the end):
    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_dm_ticket_cards_pg.py --dsn postgresql://…@127.0.0.1:55432/predvestnik_preprod

Proves: on a database that already has the S23b `dm_tickets` (as prod does) the schema call adds `dm_ticket_cards` and keeps
the tickets; a second call changes nothing; twelve simultaneous tickets give one staff member exactly CARDS_PER_HOUR cards
(the last marked «last»), the rest wait; a released card frees its slot; an hour later the cards come again; deleting
a ticket (account deletion) removes its cards; a page number past the end shows the last page.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused@127.0.0.1/unused")

from core import dm_tickets as rules  # noqa: E402
from infrastructure.pg_adapter import PGAdapter  # noqa: E402

SCHEMA = "s23d_ticket_cards_proof"
STAFF = 983100


async def run(dsn: str) -> None:
    if urlparse(dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("only a loopback PostgreSQL DSN is allowed")
    os.environ["DATABASE_URL"] = dsn
    from infrastructure.database import create_pool, get_pool
    from infrastructure.repositories import dm_tickets as repo
    from services import dm_tickets as service
    await create_pool()

    @asynccontextmanager
    async def database():
        async with get_pool().acquire() as connection:
            await connection.execute(f"SET search_path TO {SCHEMA}")
            try:
                yield PGAdapter(connection)
            finally:
                await connection.execute("RESET search_path")

    async with get_pool().acquire() as connection:
        await connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        await connection.execute(f"CREATE SCHEMA {SCHEMA}")
    try:
        async with database() as db:
            await db.execute("CREATE TABLE users (user_tg_id BIGINT PRIMARY KEY, user_tg_username TEXT, user_tg_name TEXT, bot_rank INT)")
            await db.execute("""CREATE TABLE dm_tickets (id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL, text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'answered', 'closed')), answer TEXT, handled_by BIGINT,
                handled_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")      # the S23b table, as on prod
            await db.execute("INSERT INTO dm_tickets (user_id, text) VALUES (1, 'обращение до S23d')")
            await repo.ensure_schema(db)
            async with db.execute("SELECT to_regclass('dm_ticket_cards') IS NOT NULL, (SELECT COUNT(*) FROM dm_tickets)") as c:
                made, kept = await c.fetchone()
            assert made and kept == 1, f"S23b database: cards table {made}, tickets kept {kept}"
            index_sql = f"SELECT COUNT(*) FROM pg_indexes WHERE schemaname = '{SCHEMA}'"
            async with db.execute(index_sql) as c:
                indexes = (await c.fetchone())[0]
            await repo.ensure_schema(db)
            async with db.execute(index_sql) as c:
                assert (await c.fetchone())[0] == indexes, "a second schema call changes nothing"
            await db.execute("DELETE FROM dm_tickets")
            ids = [await repo.add(db, 100 + n, f"обращение номер {n:02d}") for n in range(rules.CARDS_PER_HOUR + 4)]
        print("PASS the cards table appears next to the S23b tickets; the schema call is idempotent")

        async def reserve(ticket_id: int) -> str:
            async with database() as db:
                return await service.reserve_card(db, ticket_id, STAFF)

        got = await asyncio.gather(*(reserve(t) for t in ids))
        assert (got.count("send"), got.count("last"), got.count("limited")) == (rules.CARDS_PER_HOUR - 1, 1, 4), got
        print(f"PASS {len(ids)} simultaneous tickets: {rules.CARDS_PER_HOUR} cards (the last one marked), 4 wait in the list")

        async with database() as db:
            sent = [t for t, slot in zip(ids, got) if slot != "limited"]
            waiting = [t for t, slot in zip(ids, got) if slot == "limited"]
            await service.release_card(db, sent[0], STAFF)                        # that card did not reach a closed DM
            assert await service.reserve_card(db, waiting[0], STAFF) == "last", "a released card frees its slot"
            assert await service.reserve_card(db, waiting[1], STAFF) == "limited"
            await db.execute("UPDATE dm_ticket_cards SET sent_at = sent_at - INTERVAL '61 minutes' WHERE staff_id = ?", (STAFF,))
            assert await service.reserve_card(db, waiting[1], STAFF) == "send", "an hour later the cards come again"
            await db.execute("DELETE FROM dm_tickets WHERE id = ?", (waiting[0],))   # account deletion of the asker
            async with db.execute("SELECT COUNT(*) FROM dm_ticket_cards WHERE ticket_id = ?", (waiting[0],)) as c:
                assert (await c.fetchone())[0] == 0, "deleting a ticket removes its cards"
            await db.execute("UPDATE dm_ticket_cards SET sent_at = sent_at - INTERVAL '2 days' WHERE ticket_id = ?", (waiting[1],))
            await service.reserve_card(db, waiting[2], STAFF)
            async with db.execute("SELECT COUNT(*) FROM dm_ticket_cards WHERE ticket_id = ?", (waiting[1],)) as c:
                assert (await c.fetchone())[0] == 0, "rows older than a day are cleaned up"
        print("PASS a failed card frees its slot; the hour rolls; a deleted ticket takes its cards; old rows are cleaned")

        async with database() as db:
            last = await service.open_page(db, 99)
            first = await service.open_page(db, 0)
            assert (last["page"], last["pages"]) == (2, 2) and len(last["items"]) == last["total"] - rules.LIST_LIMIT, last
            assert first["page"] == 1 and len(first["items"]) == rules.LIST_LIMIT and first["items"][0]["text"].endswith("00")
            await db.execute("UPDATE dm_tickets SET status = 'closed'")
            empty = await service.open_page(db, 3)
            assert (empty["items"], empty["total"], empty["page"], empty["pages"]) == ([], 0, 1, 1), empty
        print("PASS pages: oldest first, a number past the end shows the last page, an empty list is one empty page")
    finally:
        async with get_pool().acquire() as connection:
            await connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
    print("PASS ticket cards and pages on PostgreSQL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(run(parser.parse_args().dsn))
