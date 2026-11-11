#!/usr/bin/env python3
"""Real PostgreSQL proof of chips in games for two (S29a, services/pair_games.py): money moves exactly once.

Run on a loopback database (it commits; players are created with ids 984xxx and their rows are removed at the end):
    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_pair_games_pg.py --dsn postgresql://…@127.0.0.1:55432/predvestnik_preprod

Proves: an invitation takes nothing; five simultaneous «Принять» take one stake from each player once; a shortage on one side
takes nothing from anybody; simultaneous final moves pay the winner once; free chips are won as free chips and bought chips
stay bought; a draw in tic-tac-toe and an expired game give both stakes back; a second expiry pass changes nothing.
"""
from __future__ import annotations

import argparse
import asyncio
import os
from urllib.parse import urlparse

os.environ.setdefault("BOT_TOKEN", "1:x")
os.environ.setdefault("DATABASE_URL", "postgresql://unused@127.0.0.1/unused")

from infrastructure.pg_adapter import PGAdapter  # noqa: E402

OWNER, FRIEND, POOR = 984001, 984002, 984003


async def run(dsn: str) -> None:
    if urlparse(dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("only a loopback PostgreSQL DSN is allowed")
    os.environ["DATABASE_URL"] = dsn
    from infrastructure.database import create_pool, get_pool
    from infrastructure.repositories import casino_v1, pair_games as games_repo
    from services import pair_games
    await create_pool()

    async def with_db(fn):
        async with get_pool().acquire() as connection:
            return await fn(PGAdapter(connection))

    async def put(db, user, bonus=0, bought=0):
        async with db.connection.transaction():
            await casino_v1.lock_wallet(db, user)
            await db.execute("UPDATE casino_v1_wallets SET chips = ?, redeemable_chips = ? WHERE user_id = ?", (bonus + bought, bought, user))

    async def wallet(user) -> tuple[int, int]:
        async def go(db):
            found = await pair_games.chip_balance(db, user)
            return found["bonus"], found["redeemable"]
        return await with_db(go)

    async def setup(db):
        await casino_v1.ensure_tables(db)
        await games_repo.ensure_schema(db)
        for user in (OWNER, FRIEND, POOR):
            await db.execute("INSERT INTO users (user_tg_id) VALUES (?) ON CONFLICT DO NOTHING", (user,))
        await db.execute("DELETE FROM pair_games WHERE owner_id = ANY(?)", ([OWNER, FRIEND, POOR],))
        await put(db, OWNER, bonus=1000, bought=500)
        await put(db, FRIEND, bonus=1000, bought=500)
        await put(db, POOR, bonus=10)

    async def invite(db, kind="rps", stake=100, funds="bonus", partner=FRIEND, allowed=True):
        return await pair_games.invite(db, connection_id="bc-pg-test", chat_id=partner, owner_id=OWNER, partner_id=partner,
                                       kind=kind, stake=stake, funds=funds, names={"owner": "A", "partner": "B"}, mora_transferable=allowed)

    try:
        await with_db(setup)
        game = await with_db(lambda db: invite(db))
        assert await wallet(OWNER) == (1000, 500), "an invitation takes nothing"

        async def accept(_):
            async def go(db):
                try:
                    await pair_games.accept(db, game["id"], FRIEND)
                    return "ok"
                except pair_games.MoveError:
                    return "refused"
            return await with_db(go)
        got = await asyncio.gather(*(accept(n) for n in range(5)))
        assert got.count("ok") == 1, got
        assert await wallet(OWNER) == (900, 500) and await wallet(FRIEND) == (900, 500), (await wallet(OWNER), await wallet(FRIEND))
        print("PASS five simultaneous «Принять» take one free stake from each player once")

        poor = await with_db(lambda db: invite(db, partner=POOR))
        try:
            await with_db(lambda db: pair_games.accept(db, poor["id"], POOR))
            raise AssertionError("a player without chips must be refused")
        except pair_games.MoveError:
            pass
        assert await wallet(OWNER) == (900, 500) and await wallet(POOR) == (10, 0), "a shortage takes nothing from anybody"
        print("PASS a shortage on one side takes nothing from anybody")

        await with_db(lambda db: pair_games.play(db, game["id"], OWNER, "s"))

        async def final(_):
            async def go(db):
                try:
                    _, result = await pair_games.play(db, game["id"], FRIEND, "r")
                    return result
                except pair_games.MoveError:
                    return "refused"
            return await with_db(go)
        results = await asyncio.gather(*(final(n) for n in range(5)))
        assert results.count("partner") == 1, results
        assert await wallet(FRIEND) == (1100, 500) and await wallet(OWNER) == (900, 500), (await wallet(OWNER), await wallet(FRIEND))
        print("PASS simultaneous final moves pay the winner once; free chips are won as free chips")

        ttt = await with_db(lambda db: invite(db, kind="ttt", stake=50, funds="redeemable"))
        ttt = await with_db(lambda db: pair_games.accept(db, ttt["id"], FRIEND))
        assert await wallet(OWNER) == (900, 450) and await wallet(FRIEND) == (1100, 450)
        first = ttt["state"]["turn"]
        players = {"owner": OWNER, "partner": FRIEND}
        order = [first, "partner" if first == "owner" else "owner"]
        result = None
        for n, cell in enumerate((0, 1, 2, 4, 3, 5, 7, 6, 8)):     # a full board without three in a row
            _, result = await with_db(lambda db, c=cell, s=order[n % 2]: pair_games.play(db, ttt["id"], players[s], str(c)))
        assert result == "draw", result
        assert await wallet(OWNER) == (900, 500) and await wallet(FRIEND) == (1100, 500), "a draw gives both bought stakes back"
        print("PASS a draw in tic-tac-toe gives both bought stakes back")

        stall = await with_db(lambda db: invite(db, kind="ttt", stake=50, funds="redeemable"))
        stall = await with_db(lambda db: pair_games.accept(db, stall["id"], FRIEND))
        mover = stall["state"]["turn"]
        await with_db(lambda db: pair_games.play(db, stall["id"], players[mover], "4"))
        await with_db(lambda db: db.execute("UPDATE pair_games SET updated_at = NOW() - INTERVAL '25 hours' WHERE id = ?", (stall["id"],)))
        await with_db(pair_games.expire_due)
        stalled = await with_db(lambda db: pair_games.get(db, stall["id"]))
        assert stalled["status"] == "finished" and stalled["winner"] == mover, stalled
        assert await wallet(players[mover]) == ((900, 550) if mover == "owner" else (1100, 550)), "the player who stopped moving loses"
        loser = "partner" if mover == "owner" else "owner"
        assert await wallet(players[loser]) == ((900, 450) if loser == "owner" else (1100, 450))
        print("PASS tic-tac-toe abandoned mid-game: the player whose turn it was loses (no escaping a loss by silence)")

        try:
            await with_db(lambda db: invite(db, kind="rps", stake=10, funds="redeemable", allowed=False))
            raise AssertionError("bought chips must follow the Mora transfer switch")
        except pair_games.MoveError:
            pass
        print("PASS bought-chip games are closed while Mora transfers are switched off")

        before = (await wallet(OWNER), await wallet(FRIEND))
        old = await with_db(lambda db: invite(db, kind="dice", stake=10, funds="redeemable"))
        await with_db(lambda db: pair_games.accept(db, old["id"], FRIEND))
        await with_db(lambda db: db.execute("UPDATE pair_games SET updated_at = NOW() - INTERVAL '25 hours' WHERE id = ?", (old["id"],)))
        closed = await with_db(pair_games.expire_due)
        again = await with_db(pair_games.expire_due)
        assert any(g["id"] == old["id"] for g in closed) and not any(g["id"] == old["id"] for g in again)
        assert (await wallet(OWNER), await wallet(FRIEND)) == before, "expiry gives both stakes back once"
        print("PASS an expired game gives both stakes back; a second pass changes nothing")
    finally:
        async def clean(db):
            await db.execute("DELETE FROM pair_games WHERE owner_id = ANY(?)", ([OWNER, FRIEND, POOR],))
            async with db.connection.transaction():
                await db.execute("SELECT set_config('predvestnik.casino_wallet_version', '2', true)")
                await db.execute("DELETE FROM casino_v1_wallets WHERE user_id = ANY(?)", ([OWNER, FRIEND, POOR],))
            await db.execute("DELETE FROM league_pass_receipts WHERE user_id = ANY(?)", ([OWNER, FRIEND, POOR],))
        await with_db(clean)
    print("PASS chips in games for two on PostgreSQL")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(run(parser.parse_args().dsn))
