"""Casino on real PostgreSQL (initialized local schema `predvestnik`, e.g. after tools/ui_stand.py):
gift once a day, Мора → chips debited once, daily cap, round replay, no negative chips under parallel bets."""
import argparse
import asyncio
from uuid import uuid4
from urllib.parse import urlparse

import asyncpg
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import casino_v1 as repo
from services import casino_v1 as casino


async def refused(coro, text=""):
    try:
        await coro
    except casino.CasinoError as exc:
        assert text in str(exc), exc
        return
    raise AssertionError("accepted: " + text)


async def connect(dsn):
    conn = await asyncpg.connect(dsn, server_settings={"search_path": "predvestnik,public"})
    return conn, PGAdapter(conn)


async def run(dsn):
    assert urlparse(dsn).hostname in {"127.0.0.1", "localhost", "::1"}
    c, db = await connect(dsn)
    uid = 991_500_000 + int(uuid4().int % 100_000)
    try:
        await repo.ensure_tables(db)
        await c.execute("INSERT INTO users(user_tg_id,user_balance_mora) VALUES($1,5000) ON CONFLICT (user_tg_id) DO UPDATE SET user_balance_mora=5000", uid)
        me = await casino.overview(db, uid)
        assert me["wallet"] == {"chips": 0, "gift_ready": True, "buy_left": 20_000} and me["rules"]["slots"]["rtp"] == 95.6
        await refused(casino.play(db, uid, game="slots", stake=100, params={}, action_id="bet-before-chips"), "Не хватает жетонов")
        gift = await casino.claim_gift(db, uid)
        assert gift["wallet"]["chips"] == 1000 and not gift["wallet"]["gift_ready"]
        await refused(casino.claim_gift(db, uid), "уже получен")
        # Мора → chips: debited exactly once per action id, refused beyond the daily cap and beyond the balance.
        first = await casino.buy_chips(db, uid, mora=1000, action_id="buy-0001")
        again = await casino.buy_chips(db, uid, mora=1000, action_id="buy-0001")
        assert first["wallet"]["chips"] == again["wallet"]["chips"] == 11_000 and again["replayed"]
        assert int(await c.fetchval("SELECT user_balance_mora FROM users WHERE user_tg_id=$1", uid)) == 4000
        await refused(casino.buy_chips(db, uid, mora=500, action_id="buy-0001"), "другой покупки")
        await casino.buy_chips(db, uid, mora=1000, action_id="buy-0002")
        await refused(casino.buy_chips(db, uid, mora=100, action_id="buy-0003"), "Сегодня можно купить ещё 0")
        await c.execute("UPDATE casino_v1_wallets SET buy_day=buy_day-1 WHERE user_id=$1", uid)   # next day
        await c.execute("UPDATE users SET user_balance_mora=50 WHERE user_tg_id=$1", uid)
        await refused(casino.buy_chips(db, uid, mora=100, action_id="buy-0004"), "Не хватает Моры")
        assert int(await c.fetchval("SELECT chips FROM casino_v1_wallets WHERE user_id=$1", uid)) == 21_000
        # Rounds: the stake and the win settle together; a retry returns the same round, never a second draw.
        r1 = await casino.play(db, uid, game="dice", stake=1000, params={"chance": 50}, action_id="bet-0001")
        r2 = await casino.play(db, uid, game="dice", stake=1000, params={"chance": 50}, action_id="bet-0001")
        assert r2["replayed"] and r2["round"] == r1["round"] and r2["wallet"]["chips"] == r1["wallet"]["chips"]
        assert r1["wallet"]["chips"] == 21_000 - 1000 + r1["round"]["payout"]
        await refused(casino.play(db, uid, game="wheel", stake=1000, params={}, action_id="bet-0001"), "другой ставки")
        await refused(casino.play(db, uid, game="slots", stake=7, params={}, action_id="bet-0002"), "ставку")
        await refused(casino.play(db, uid, game="dice", stake=10, params={"chance": 33}, action_id="bet-0003"), "шанс")
        # Parallel bets from five connections on 2 500 chips: the balance never goes below zero.
        await c.execute("UPDATE casino_v1_wallets SET chips=2500 WHERE user_id=$1", uid)
        pool = [await connect(dsn) for _ in range(5)]
        try:
            results = await asyncio.gather(*(casino.play(adb, uid, game="slots", stake=1000, params={}, action_id=f"race-{i:04d}")
                                             for i, (_, adb) in enumerate(pool)), return_exceptions=True)
        finally:
            for conn, _ in pool:
                await conn.close()
        played = [r for r in results if isinstance(r, dict)]
        assert played and all(isinstance(r, (dict, casino.CasinoError)) for r in results), results
        chips = int(await c.fetchval("SELECT chips FROM casino_v1_wallets WHERE user_id=$1", uid))
        expected = 2500 - 1000 * len(played) + sum(r["round"]["payout"] for r in played)
        assert chips == expected >= 0, (chips, expected)
        staked, paid = await c.fetchrow("SELECT total_staked,total_paid FROM casino_v1_wallets WHERE user_id=$1", uid)
        rounds = await c.fetch("SELECT stake,payout FROM casino_v1_rounds WHERE user_id=$1", uid)
        assert int(staked) == sum(int(r["stake"]) for r in rounds) and int(paid) == sum(int(r["payout"]) for r in rounds)
        view = await casino.overview(db, uid)
        assert view["recent"] and view["wallet"]["chips"] == chips
    finally:
        for table in ("casino_v1_rounds", "casino_v1_purchases", "casino_v1_wallets"):
            await c.execute(f"DELETE FROM {table} WHERE user_id=$1", uid)
        await c.close()
    print("OK: casino on PostgreSQL — gift once a day, Мора debited once, cap, replayed rounds, parallel bets never below zero")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(run(parser.parse_args().dsn))
