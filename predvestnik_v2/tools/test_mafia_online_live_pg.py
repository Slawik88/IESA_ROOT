"""Committed invalidations, private recipients and deadline wakeups on disposable PG."""
import argparse
import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

os.environ.setdefault("BOT_TOKEN", "1:x")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import mafia_online as repo
from infrastructure.repositories.balance_events import CHANNEL
from services import mafia_online as game, mafia_online_chat as chat, mafia_online_scheduler as scheduler


async def main(dsn):
    schema = "mafia_live_" + uuid.uuid4().hex[:12]
    admin = await asyncpg.connect(dsn)
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    options = {"search_path": schema}
    writer = await asyncpg.connect(dsn, server_settings=options)
    observer = await asyncpg.connect(dsn, server_settings=options)
    events, wakeups = [], []
    await observer.add_listener(CHANNEL, lambda _c, _p, _ch, body: events.append(json.loads(body)))
    await observer.add_listener(repo.SCHEDULE_CHANNEL, lambda *_args: wakeups.append(True))
    db = PGAdapter(writer)

    async def drain():
        # A round trip makes pending PG notifications visible without a long test sleep.
        await observer.fetchval("SELECT 1")
        await asyncio.sleep(.03)
        out = events[:]
        events.clear()
        return out

    try:
        await repo.ensure_tables(db)
        room = await game.create(db, {"id": 1, "first_name": "Лиса"}, seats=8)
        for uid in range(2, 9):
            await game.join(db, room, {"id": uid, "first_name": f"Гость {uid}"})
        state = await repo.load(db, room)
        team = [p for p in state["players"] if p["role"] in ("mafia", "don")]
        await drain()
        before = state["version"]
        await chat.send(db, room, team[0]["id"], "mafia", "Тайный разговор", uuid.uuid4())
        received = await drain()
        assert {e["user_id"] for e in received} == {p["id"] for p in team}
        assert all(set(e) == {"type", "user_id", "room_id", "version"} for e in received)
        assert all(e["version"] == before for e in received), "chat must invalidate even without a version bump"
        await game.get(db, room, 1)
        assert not await drain(), "presence/GET must never cause an invalidation loop"
        async with writer.transaction():
            state = await repo.load(db, room, lock=True)
            state["phase"] = "discussion"
            await repo.save(db, state)
        assert {e["user_id"] for e in await drain()} == set(range(1, 9))
        nonce = uuid.uuid4()
        public_uid = next(p["id"] for p in state["players"] if p["id"] != team[0]["id"])
        await chat.send(db, room, public_uid, "table", "Общий разговор", nonce)
        assert {e["user_id"] for e in await drain()} == set(range(1, 9))
        await chat.send(db, room, public_uid, "table", "Общий разговор", nonce)
        assert not await drain(), "a replay must not send another invalidation"
        try:
            async with writer.transaction():
                state = await repo.load(db, room, lock=True)
                await repo.save(db, state)
                raise ValueError("rollback")
        except ValueError:
            pass
        assert not await drain(), "rolled back state must never be announced"
        await game.control(db, room, 1, "cancel")
        assert not await repo.current(db, 1)
        assert {e["user_id"] for e in await drain()} == set(range(1, 9)), "finale survives deleted seats"
        assert wakeups, "committed room/deadline changes wake the lifecycle"
        print("PASS committed/private/same-version chat invalidations, quiet heartbeat, replay, rollback and finale recipients")

        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=3, server_settings=options)
        listeners = []

        async def connect():
            connection = await asyncpg.connect(dsn, server_settings=options)
            listeners.append(connection)
            return connection

        with patch.object(scheduler, "get_pool", return_value=pool), patch.object(scheduler, "connect_direct", connect):
            task = asyncio.create_task(scheduler.run())
            try:
                while not listeners:
                    await asyncio.sleep(.01)
                await asyncio.sleep(.05)
                # Scheduler is waiting with no active rooms. Creating and then shortening
                # a deadline must interrupt that wait, rather than wait for a 30s rescan.
                pending = await game.create(db, {"id": 20, "first_name": "Таймер"})
                started = time.monotonic()
                async with writer.transaction():
                    state = await repo.load(db, pending, lock=True)
                    state["deadline"] = await repo.now(db) + .3
                    await repo.save(db, state)
                while (await repo.load(db, pending))["phase"] == "lobby":
                    assert time.monotonic() - started < 1.5, "missed deadline wakeup"
                    await asyncio.sleep(.02)
                elapsed = time.monotonic() - started
                listeners[-1].terminate()
                started = time.monotonic()
                while len(listeners) < 2:
                    assert time.monotonic() - started < 3, "listener did not reconnect"
                    await asyncio.sleep(.02)
                print(f"PASS empty scheduler wakes for a new/shortened deadline ({elapsed:.2f}s), LISTEN reconnects outside pool")
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                await pool.close()
    finally:
        await writer.close()
        await observer.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    args = parser.parse_args()
    if urlparse(args.dsn).hostname not in ("127.0.0.1", "localhost", "::1"):
        raise SystemExit("loopback PostgreSQL required")
    asyncio.run(main(args.dsn))
