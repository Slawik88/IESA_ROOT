"""Real PostgreSQL proof for expedition route rewards: odds server-side, one payout per run, weekly cap, flag."""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.pet_routes_v1 import FLAG, WEEKLY_CAP_MORA
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import economy_ledger, system_flags
from infrastructure.repositories import pets_v1 as repo
from services import pets_v1


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def mora(db, user: int) -> int:
    async with db.execute("SELECT user_balance_mora FROM users WHERE user_tg_id=?", (user,)) as c:
        return int((await c.fetchone())[0])


START: dict[int, int] = {}


async def gained(db, user: int) -> int:
    """Mora paid by route rewards; other systems (achievements) may also move the balance, so the
    route table is cross-checked against the ledger operations of this reason instead."""
    async with db.execute("SELECT COALESCE(SUM(paid_mora),0), COUNT(*) FILTER (WHERE paid_mora>0) "
                          "FROM pet_v1_route_rewards WHERE user_id=? AND run_id<>'old-cap-run'", (user,)) as c:
        paid, rows = await c.fetchone()
    async with db.execute("SELECT COUNT(*) FROM economic_operations WHERE user_id=? AND reason_code='pet_route_reward'", (user,)) as c:
        assert (await c.fetchone())[0] == rows, "every paid route has exactly one ledger operation"
    if rows:
        assert await mora(db, user) - START[user] >= paid
    return int(paid)


async def ready_expedition(db, user: int, tag: str, hours: int = 6, level: int = 1) -> int:
    await db.execute("INSERT INTO users(user_tg_id) VALUES (?) ON CONFLICT(user_tg_id) DO NOTHING", (user,))
    async with db.execute("SELECT id FROM pets WHERE owner_id=?", (user,)) as c:
        row = await c.fetchone()
    if row is None:
        await db.execute("INSERT INTO pets(owner_id,name,species_id,rarity) VALUES (?,?,?,?)", (user, "R", "cat", "common"))
        async with db.execute("SELECT id FROM pets WHERE owner_id=?", (user,)) as c:
            row = await c.fetchone()
    pet = row[0]
    await pets_v1.select_active_pet(db, user, pet, f"act-{tag}")
    await db.execute("UPDATE pet_v1_state SET level=?,endurance=100 WHERE user_id=? AND pet_id=?", (level, user, pet))
    await pets_v1.start_activity(db, user_id=user, kind="expedition", hours=hours, action_id=f"exp-{tag}")
    await db.execute("UPDATE pet_v1_runs SET status='ready',ready_at=NOW(),ends_at=NOW()-INTERVAL '1 second' "
                     "WHERE user_id=? AND status='active'", (user,))
    START[user] = await mora(db, user)
    return pet


async def run(dsn: str) -> None:
    conn = await asyncpg.connect(dsn)
    db = PGAdapter(conn)
    tx = conn.transaction()
    await tx.start()
    real_randbelow = pets_v1.secrets.randbelow
    try:
        await economy_ledger.ensure_tables(db)
        await repo.ensure_tables(db)
        await system_flags.ensure_table(db)

        async def must_reject(coro) -> None:
            try:
                async with db.connection.transaction():
                    await coro
            except Exception:
                return
            raise AssertionError("expected a rejection")

        def roll(value: int):
            pets_v1.secrets.randbelow = lambda n, _v=value: _v

        # flag off: the choice works as before and pays nothing
        await db.execute("UPDATE system_flags SET enabled=0 WHERE key=?", (FLAG,))
        off_user = 977001
        await ready_expedition(db, off_user, "off")
        off = await pets_v1.choose_expedition(db, user_id=off_user, decision="steady", action_id="ch-off")
        assert off["route"] is None and await gained(db, off_user) == 0
        await must_reject(pets_v1.choose_expedition(db, user_id=off_user, decision="scout", action_id="scout-off"))

        await db.execute("UPDATE system_flags SET enabled=1 WHERE key=?", (FLAG,))

        # success pays the exact table value once; a replay and a second choice pay nothing more
        ok_user = 977002
        await ready_expedition(db, ok_user, "ok", hours=6)
        view = await pets_v1.overview(db, ok_user)
        assert view["route_options"]["rewards_enabled"] and all("chance_percent" not in r for r in view["route_options"]["routes"]), \
            "no hint charge at level 1: exact odds stay hidden"
        roll(0)
        won = await pets_v1.choose_expedition(db, user_id=ok_user, decision="steady", action_id="ch-ok")
        assert won["route"]["success"] and won["route"]["paid_mora"] == 100 and won["route"]["chance_percent"] == 80
        assert await gained(db, ok_user) == 100
        again = await pets_v1.choose_expedition(db, user_id=ok_user, decision="steady", action_id="ch-ok")
        assert again["idempotent_replay"] and await gained(db, ok_user) == 100
        await must_reject(pets_v1.choose_expedition(db, user_id=ok_user, decision="bold", action_id="ch-ok-2"))
        assert await gained(db, ok_user) == 100
        async with db.execute("SELECT COUNT(*) FROM pet_v1_route_rewards WHERE user_id=?", (ok_user,)) as c:
            assert (await c.fetchone())[0] == 1
        async with db.execute("SELECT COUNT(*) FROM economic_operations WHERE user_id=? AND reason_code='pet_route_reward'", (ok_user,)) as c:
            assert (await c.fetchone())[0] == 1

        # failure pays nothing and takes nothing
        fail_user = 977003
        await ready_expedition(db, fail_user, "fail", hours=9)
        roll(99)
        lost = await pets_v1.choose_expedition(db, user_id=fail_user, decision="careful", action_id="ch-fail")
        assert lost["route"]["success"] is False and lost["route"]["paid_mora"] == 0 and await gained(db, fail_user) == 0

        # level 4: the hint shows the exact odds; level 8: risk guard +5 points; level 16: +15% reward
        hint_user = 977004
        await ready_expedition(db, hint_user, "hint", hours=3, level=16)
        view = await pets_v1.overview(db, hint_user)
        by_id = {r["id"]: r for r in view["route_options"]["routes"]}
        assert set(by_id) == {"careful", "steady", "bold", "scout"}
        assert by_id["steady"] == {"id": "steady", "chance_percent": 85, "reward_mora": 58}, by_id["steady"]
        assert by_id["careful"]["chance_percent"] == 99, "p is capped at 0.99"
        assert view["route_options"]["weekly_remaining_mora"] == WEEKLY_CAP_MORA
        roll(0)
        top = await pets_v1.choose_expedition(db, user_id=hint_user, decision="scout", action_id="ch-scout")
        assert top["route"]["success"] and top["route"]["paid_mora"] == 46 and top["route"]["chance_percent"] == 95

        # scout is a level-12 option
        low_user = 977005
        await ready_expedition(db, low_user, "low", level=11)
        await must_reject(pets_v1.choose_expedition(db, user_id=low_user, decision="scout", action_id="ch-low"))
        still = (await pets_v1.overview(db, low_user))["activity"]
        assert still["status"] == "ready" and still["decision"] is None, "a rejected scout leaves the route choice open"

        # weekly cap: the payout is cut at the cap, not rejected
        cap_user = 977006
        await ready_expedition(db, cap_user, "cap", hours=9)
        await db.execute(
            "INSERT INTO pet_v1_runs(id,user_id,pet_id,kind,duration_hours,status,starts_at,ends_at) "
            "SELECT 'old-cap-run',?,id,'expedition',3,'claimed',NOW(),NOW() FROM pets WHERE owner_id=?", (cap_user, cap_user))
        await repo.save_route_reward(
            db, run_id="old-cap-run", user_id=cap_user, route="steady", hours=3, chance_percent=80, success=True,
            reward_mora=WEEKLY_CAP_MORA - 30, paid_mora=WEEKLY_CAP_MORA - 30, economy_operation_id=None, policy_version="t")
        roll(0)
        capped = await pets_v1.choose_expedition(db, user_id=cap_user, decision="steady", action_id="ch-cap")
        assert capped["route"]["paid_mora"] == 30 and capped["route"]["capped"] and await gained(db, cap_user) == 30
    finally:
        pets_v1.secrets.randbelow = real_randbelow
        await tx.rollback()
        await conn.close()
    print("OK: route rewards are server-rolled, paid once per run, hidden/hinted by level, capped weekly and flag-gated")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, required=True)
    asyncio.run(run(parser.parse_args().dsn))
