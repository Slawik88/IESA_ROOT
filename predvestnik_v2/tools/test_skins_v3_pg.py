#!/usr/bin/env python3
"""PostgreSQL proof for Skins V3: buy, equip, tier upgrades, Essence, and the launch refund migration."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.skins_v3 import BUY_PRICE_ZARNIKI, ESSENCE_PER_ZARNIK, SET_BONUS_ESSENCE, UPGRADE_ESSENCE  # noqa: E402
from infrastructure.pg_adapter import PGAdapter  # noqa: E402
from infrastructure.repositories import economy_ledger  # noqa: E402
from infrastructure.repositories import global_skins_v1 as old_skins  # noqa: E402
from infrastructure.repositories import skins_v3 as repo  # noqa: E402
from services import skins_v3 as skins  # noqa: E402
from services import skins_v3_migration as migration  # noqa: E402


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def zarniki(db, uid: int) -> int:
    async with db.execute("SELECT COALESCE(user_balance_zarniki,0) FROM users WHERE user_tg_id=?", (uid,)) as c:
        return int((await c.fetchone())[0])


async def expect_conflict(coro, fragment: str) -> None:
    try:
        await coro
    except skins.SkinConflict as exc:
        assert fragment in str(exc), (fragment, str(exc))
    else:
        raise AssertionError(f"expected conflict: {fragment}")


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await economy_ledger.ensure_tables(db)
    await old_skins.ensure_tables(db)
    await migration.ensure_tables(db)
    outer = connection.transaction()
    await outer.start()
    try:
        user = 981001
        await db.execute("INSERT INTO users(user_tg_id,user_tg_username,user_balance_zarniki) VALUES (?,?,?) ON CONFLICT (user_tg_id) DO UPDATE SET user_balance_zarniki=EXCLUDED.user_balance_zarniki", (user, "skin_v3", 1000))

        initial = await skins.state(db, user)
        assert len(initial["items"]) == 25 and len(initial["sets"]) == 2 and not any(i["owned"] for i in initial["items"]) and initial["essence"]["balance"] == 0
        assert initial["equipped"] is None and initial["zarniki"] == 1000

        # buy: charged once, owned at D, equipped; repeating the same request does not charge twice
        _, state = await skins.buy(db, user, "threshold", idempotency_key="k-buy-1")
        assert await zarniki(db, user) == 1000 - BUY_PRICE_ZARNIKI["C"]
        item = next(i for i in state["items"] if i["id"] == "threshold")
        assert item["owned"] and item["level"] == "D" and item["equipped"] and item["next"] == {"tier": "C", "essence": UPGRADE_ESSENCE["C"], "needs_vip": False}
        await skins.buy(db, user, "threshold", idempotency_key="k-buy-1")
        assert await zarniki(db, user) == 1000 - BUY_PRICE_ZARNIKI["C"]
        await expect_conflict(skins.buy(db, user, "threshold", idempotency_key="k-buy-2"), "уже у вас")
        await expect_conflict(skins.buy(db, user, "starheart", idempotency_key="k-buy-3"), "Нужно 900")
        await expect_conflict(skins.upgrade(db, user, "threshold", idempotency_key="u0"), "Эссенции")

        # Essence for Zarniki, then upgrades
        _, state = await skins.buy_essence(db, user, 10, idempotency_key="e1")
        assert state["essence"]["balance"] == 10 * ESSENCE_PER_ZARNIK and await zarniki(db, user) == 1000 - 160 - 10
        await skins.buy_essence(db, user, 10, idempotency_key="e1")
        assert (await skins.state(db, user))["essence"]["balance"] == 40, "essence purchase must be idempotent"
        await expect_conflict(skins.buy_essence(db, user, 7, idempotency_key="e2"), "набора")
        _, state = await skins.upgrade(db, user, "threshold", idempotency_key="u1")
        item = next(i for i in state["items"] if i["id"] == "threshold")
        assert item["level"] == "C" and item["maxed"] and state["essence"]["balance"] == 40 - UPGRADE_ESSENCE["C"]
        await skins.upgrade(db, user, "threshold", idempotency_key="u1")
        assert (await skins.state(db, user))["essence"]["balance"] == 40 - UPGRADE_ESSENCE["C"], "upgrade replay must not charge again"
        await expect_conflict(skins.upgrade(db, user, "threshold", idempotency_key="u2"), "максимальном")
        await expect_conflict(skins.upgrade(db, user, "void", idempotency_key="u3"), "Сначала купите")

        # equip / unequip, and ownership is required
        await expect_conflict(skins.equip(db, user, "void"), "ещё не куплен")
        assert (await skins.equip(db, user, None))["equipped"] is None
        assert (await skins.equip(db, user, "threshold"))["equipped"] == "threshold"
        look = await skins.own_look(db, user)
        assert look["id"] == "threshold" and look["tier"] == "C" and look["tokens"]["--v3-bg"]

        # quest reward Essence is granted once per reward id
        assert await skins.grant_essence_in_transaction(db, user, 5, reason="quest_reward", reference="daily:2026-10-08") == 5
        assert await skins.grant_essence_in_transaction(db, user, 5, reason="quest_reward", reference="daily:2026-10-08") == 0
        assert (await repo.essence_balance(db, user)) == 40 - UPGRADE_ESSENCE["C"] + 5

        # themed set: the purchase that completes it pays Essence exactly once
        await db.execute("UPDATE users SET user_balance_zarniki=5000 WHERE user_tg_id=?", (user,))
        before_essence = await repo.essence_balance(db, user)
        for n, sid in enumerate(("lotus_pond", "lotus_gold")):
            await skins.buy(db, user, sid, idempotency_key=f"set-{n}")
        assert await repo.essence_balance(db, user) == before_essence, "no bonus before the set is complete"
        message, state = await skins.buy(db, user, "moon_lotus", idempotency_key="set-2")
        assert await repo.essence_balance(db, user) == before_essence + SET_BONUS_ESSENCE and "собран" in message
        assert next(s for s in state["sets"] if s["id"] == "lotus")["complete"] and next(s for s in state["sets"] if s["id"] == "sakura")["have"] == 0
        await skins.buy(db, user, "moon_lotus", idempotency_key="set-2")           # replay
        assert await repo.essence_balance(db, user) == before_essence + SET_BONUS_ESSENCE, "bonus is paid once"

        # ── launch migration ────────────────────────────────────────────────────────────────────────────────
        payer, free_user, covered = 981002, 981003, 981004
        for uid in (payer, free_user, covered):
            await db.execute("INSERT INTO users(user_tg_id,user_tg_username,user_balance_zarniki) VALUES (?,?,?) ON CONFLICT (user_tg_id) DO UPDATE SET user_balance_zarniki=EXCLUDED.user_balance_zarniki", (uid, f"mig{uid}", 5000))
        for uid in (payer, free_user, covered):
            await db.execute("INSERT INTO user_cosmetics(user_id,cosmetic_id) VALUES (?,?),(?,?)", (uid, "cos_name_glow_moon", uid, "cos_avatar_frame_oak"))
            await db.execute("INSERT INTO user_cosmetic_loadout(user_id,slot,cosmetic_id) VALUES (?,?,?),(?,?,?)", (uid, "name_glow", "cos_name_glow_moon", uid, "welcome", "welcome_anim"))
        await old_skins.grant(db, payer, "void_atlas", source="purchase")
        await old_skins.set_selection(db, payer, "void_atlas")
        await economy_ledger.apply_balance_change(db, payer, {"zarniki": -250}, reason_code="cosmetic_purchase", idempotency_key="old-1", source_type="cosmetics", reference_type="cosmetic", reference_id="cos_name_glow_moon")
        await economy_ledger.apply_balance_change(db, payer, {"zarniki": -1600}, reason_code="global_skin_purchase", idempotency_key="old-2", source_type="global_skins_v1", reference_type="global_skin", reference_id="void_atlas")
        await economy_ledger.apply_balance_change(db, payer, {"zarniki": -77}, reason_code="shop_other", idempotency_key="old-3", source_type="other")   # unrelated spend is not refunded
        await economy_ledger.apply_balance_change(db, covered, {"zarniki": -400}, reason_code="cosmetic_purchase", idempotency_key="old-4", source_type="cosmetics", reference_type="cosmetic", reference_id="x")
        await db.execute("CREATE TABLE IF NOT EXISTS retirement_compensation_receipts_v2 (user_id BIGINT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL)")
        await db.execute("INSERT INTO retirement_compensation_receipts_v2(user_id, applied_at) VALUES (?, NOW() + INTERVAL '1 hour') ON CONFLICT DO NOTHING", (covered,))

        before = await zarniki(db, payer)
        plans = {p.user_id: p for p in await migration.build_plan(db)}
        assert plans[payer].refund == 1850 and plans[free_user].refund == 0 and plans[covered].refund == 0, plans
        assert user not in plans, "a player with only new skins has nothing to migrate"
        for uid in (payer, free_user, covered):
            assert await migration.apply_user(db, plans[uid]) is True
        assert await zarniki(db, payer) == before + 1850 and await zarniki(db, free_user) == 5000 and await zarniki(db, covered) == 5000 - 400
        async with db.execute("SELECT reason_code, delta FROM economic_ledger WHERE user_id=? AND reason_code=?", (payer, migration.REFUND_REASON)) as c:
            rows = await c.fetchall()
        assert len(rows) == 1 and float(rows[0][1]) == 1850
        for table in ("user_cosmetics", "global_skin_v1_owned", "global_skin_v1_selection"):
            async with db.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id IN (?,?,?)", (payer, free_user, covered)) as c:
                assert int((await c.fetchone())[0]) == 0, table
        async with db.execute("SELECT slot FROM user_cosmetic_loadout WHERE user_id IN (?,?,?)", (payer, free_user, covered)) as c:
            assert {r[0] for r in await c.fetchall()} == {"welcome"}, "only the welcome animation stays, it is not a skin"
        async with db.execute("SELECT COUNT(*) FROM skins_v3_archive_cosmetics WHERE user_id=?", (payer,)) as c:
            assert int((await c.fetchone())[0]) == 2
        async with db.execute("SELECT selected FROM skins_v3_archive_global_skins WHERE user_id=?", (payer,)) as c:
            assert (await c.fetchone())[0] is True
        async with db.execute("SELECT payload FROM web_notifications WHERE user_id=? ORDER BY id DESC LIMIT 1", (payer,)) as c:
            assert "1850" in (await c.fetchone())[0]
        again = {p.user_id for p in await migration.build_plan(db)}
        assert not ({payer, free_user, covered} & again), "migrated players must not be planned again"
        assert await migration.apply_user(db, plans[payer]) is False, "second application is a no-op"
        assert await zarniki(db, payer) == before + 1850
        print("OK: skins v3 buy/equip/upgrade/essence are idempotent; migration refunds exactly what was paid and archives the old system")
    finally:
        await outer.rollback()
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, default=os.getenv("DATABASE_URL", "postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod"))
    asyncio.run(run(parser.parse_args().dsn))
