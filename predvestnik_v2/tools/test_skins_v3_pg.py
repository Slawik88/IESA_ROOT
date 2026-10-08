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

from unittest import mock  # noqa: E402

from core.skins_v3 import BUY_PRICE_ZARNIKI, ESSENCE_PER_ZARNIK, UPGRADE_ESSENCE  # noqa: E402
from core.skins_v3_collection import featured_bonus, milestones, row_bonus, set_bonus  # noqa: E402
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
        await db.execute("INSERT INTO users(user_tg_id,user_tg_username,user_balance_zarniki) VALUES (?,?,?) ON CONFLICT (user_tg_id) DO UPDATE SET user_balance_zarniki=EXCLUDED.user_balance_zarniki", (user, "skin_v3", 3000))

        initial = await skins.state(db, user)
        assert len(initial["items"]) == 25 and len(initial["sets"]) == 2 and not any(i["owned"] for i in initial["items"]) and initial["essence"]["balance"] == 0
        assert initial["equipped"] is None and initial["zarniki"] == 3000

        # buy: charged once, owned at D, equipped; repeating the same request does not charge twice
        _, state = await skins.buy(db, user, "threshold", idempotency_key="k-buy-1")
        assert await zarniki(db, user) == 3000 - BUY_PRICE_ZARNIKI["C"]
        item = next(i for i in state["items"] if i["id"] == "threshold")
        assert item["owned"] and item["level"] == "D" and item["equipped"] and item["next"] == {"tier": "C", "essence": UPGRADE_ESSENCE["C"], "needs_vip": False}
        await skins.buy(db, user, "threshold", idempotency_key="k-buy-1")
        assert await zarniki(db, user) == 3000 - BUY_PRICE_ZARNIKI["C"]
        await expect_conflict(skins.buy(db, user, "threshold", idempotency_key="k-buy-2"), "уже у вас")
        await expect_conflict(skins.buy(db, user, "starheart", idempotency_key="k-buy-3"), f"Нужно {BUY_PRICE_ZARNIKI['SSS']}")
        await expect_conflict(skins.upgrade(db, user, "threshold", idempotency_key="u0"), "Эссенции")

        # Essence for Zarniki, then upgrades
        pack = 30
        _, state = await skins.buy_essence(db, user, pack, idempotency_key="e1")
        assert state["essence"]["balance"] == pack * ESSENCE_PER_ZARNIK and await zarniki(db, user) == 3000 - BUY_PRICE_ZARNIKI["C"] - pack
        await skins.buy_essence(db, user, pack, idempotency_key="e1")
        assert (await skins.state(db, user))["essence"]["balance"] == pack * ESSENCE_PER_ZARNIK, "essence purchase must be idempotent"
        await expect_conflict(skins.buy_essence(db, user, 7, idempotency_key="e2"), "набора")
        _, state = await skins.upgrade(db, user, "threshold", idempotency_key="u1")
        item = next(i for i in state["items"] if i["id"] == "threshold")
        left = pack * ESSENCE_PER_ZARNIK - UPGRADE_ESSENCE["C"]
        assert item["level"] == "C" and item["maxed"] and state["essence"]["balance"] == left
        assert [e["kind"] for e in state["events"]] == ["tier", "badge"] and state["events"][0]["tier"] == "C" and state["events"][0]["maxed"], "the first skin at its ceiling earns a badge"
        await skins.upgrade(db, user, "threshold", idempotency_key="u1")
        assert (await skins.state(db, user))["essence"]["balance"] == left, "upgrade replay must not charge again"
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
        assert (await repo.essence_balance(db, user)) == left + 5

        # collecting: set, rarity row and collection steps pay Essence exactly once; the week's skin is pinned so the test is stable
        steps = {m["at"]: m["essence"] for m in milestones()}
        week = {"skin_id": "starheart", "week": "2026-10-05", "ends_at": "2026-10-12T00:00:00+00:00", "bonus_essence": featured_bonus("starheart")}
        with mock.patch.object(skins, "featured", lambda now=None: week):
            await db.execute("UPDATE users SET user_balance_zarniki=30000 WHERE user_tg_id=?", (user,))
            before_essence = await repo.essence_balance(db, user)
            await skins.buy(db, user, "lotus_pond", idempotency_key="set-0")
            assert await repo.essence_balance(db, user) == before_essence, "two skins reach no step"
            message, state = await skins.buy(db, user, "lotus_gold", idempotency_key="set-1")      # third skin: first collection step
            assert await repo.essence_balance(db, user) == before_essence + steps[3] and [e["kind"] for e in state["events"]] == ["rank"]
            message, state = await skins.buy(db, user, "moon_lotus", idempotency_key="set-2")
            assert await repo.essence_balance(db, user) == before_essence + steps[3] + set_bonus("lotus") and "собран" in message
            assert [e["kind"] for e in state["events"]] == ["set"] and state["events"][0]["essence"] == set_bonus("lotus")
            lotus = next(s for s in state["sets"] if s["id"] == "lotus")
            assert lotus["complete"] and lotus["missing"] == [] and lotus["bonus_essence"] == set_bonus("lotus")
            assert next(s for s in state["sets"] if s["id"] == "sakura")["have"] == 0
            again, state = await skins.buy(db, user, "moon_lotus", idempotency_key="set-2")        # replay
            assert state["events"] == [] and await repo.essence_balance(db, user) == before_essence + steps[3] + set_bonus("lotus"), "bonus is paid once"
            look = await skins.own_look(db, user)
            assert look["id"] == "moon_lotus" and look["crest"]["id"] == "lotus", "wearing a member of a finished set shows its crest"
            first = next(i for i in (await skins.state(db, user))["items"] if i["id"] == "threshold")
            assert "crest" not in first, "a skin outside a finished set has no crest"
            # rarity row: the fourth D skin completes it; the collection summary carries counts only
            for n, sid in enumerate(("forest", "dune")):
                await skins.buy(db, user, sid, idempotency_key=f"row-{n}")
            before_row = await repo.essence_balance(db, user)
            _, state = await skins.buy(db, user, "harbor", idempotency_key="row-2")
            kinds = [e["kind"] for e in state["events"]]
            assert "row" in kinds and await repo.essence_balance(db, user) == before_row + row_bonus("D") + steps[6] * ("rank" in kinds), (kinds, state["events"])
            col = state["collection"]
            assert col["owned"] == 7 and col["rank"] == "Коллекционер" and col["rows"][0]["done"] and col["milestones"][0]["done"] and not col["milestones"][-1]["done"]
            assert col["sets_done"] == [{"id": "lotus", "name": "Сад Лотоса", "glyph": "🪷"}] and col["maxed"] == 1 and col["maxed_badge"] == "Огранщик"
            # skin of the week: the gift is paid once, only for that skin and only inside its week
            before_week = await repo.essence_balance(db, user)
            _, state = await skins.buy(db, user, "starheart", idempotency_key="week-1")
            assert any(e["kind"] == "featured" for e in state["events"]) and await repo.essence_balance(db, user) >= before_week + featured_bonus("starheart")
            assert state["featured"]["owned"] and state["featured"]["skin_id"] == "starheart"
            await skins.buy(db, user, "starheart", idempotency_key="week-1")
            before_replay = await repo.essence_balance(db, user)
            await skins.buy(db, user, "starheart", idempotency_key="week-1")
            assert await repo.essence_balance(db, user) == before_replay, "the weekly gift is never paid twice"
        # the collection summary shown to other players has no skin ids
        from services import appearance_public_v3 as public
        view = await public.public_view(db, user)
        assert view["collection"]["owned"] == 8 and "ids" not in view["collection"] and all(not isinstance(v, (list, dict)) or k == "sets_done" for k, v in view["collection"].items())

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
        # same shape as the real receipts table: one row per (snapshot, player), so a player can have several
        await db.execute("CREATE TABLE IF NOT EXISTS retirement_compensation_receipts_v2 (snapshot_id TEXT NOT NULL, user_id BIGINT NOT NULL, applied_at TIMESTAMPTZ NOT NULL, cosmetics_zarniki INTEGER NOT NULL DEFAULT 0, zarniki_carry INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(snapshot_id, user_id))")
        await db.execute("INSERT INTO retirement_compensation_receipts_v2(snapshot_id, user_id, applied_at) VALUES ('a', ?, NOW() + INTERVAL '1 hour'), ('b', ?, NOW() + INTERVAL '1 hour') ON CONFLICT DO NOTHING", (covered, covered))

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
        # earlier refunds are never paid twice, whatever the number of receipts; large refunds wait for the owner
        twice, wiped, whale = 981005, 981006, 981007
        for uid in (twice, wiped, whale):
            await db.execute("INSERT INTO users(user_tg_id,user_tg_username,user_balance_zarniki) VALUES (?,?,?) ON CONFLICT (user_tg_id) DO UPDATE SET user_balance_zarniki=EXCLUDED.user_balance_zarniki", (uid, f"mig{uid}", 5000))
            await db.execute("INSERT INTO user_cosmetics(user_id,cosmetic_id) VALUES (?,?)", (uid, "cos_name_glow_moon"))
        for n, (uid, amount) in enumerate(((twice, 300), (wiped, 700), (whale, 1200))):
            await economy_ledger.apply_balance_change(db, uid, {"zarniki": -amount}, reason_code="cosmetic_purchase", idempotency_key=f"old-x{n}", source_type="cosmetics", reference_type="cosmetic", reference_id="x")
        await db.execute("INSERT INTO retirement_compensation_receipts_v2(snapshot_id, user_id, applied_at) VALUES ('a', ?, NOW() - INTERVAL '1 hour'), ('b', ?, NOW() - INTERVAL '2 hours')", (twice, twice))
        await db.execute("CREATE TABLE IF NOT EXISTS cosmetics_lineup_wipe_log (user_id BIGINT PRIMARY KEY, processed_at TIMESTAMP DEFAULT NOW())")
        await db.execute("INSERT INTO cosmetics_lineup_wipe_log(user_id, processed_at) VALUES (?, NOW() + INTERVAL '1 hour')", (wiped,))
        plans = {p.user_id: p for p in await migration.build_plan(db)}
        assert plans[twice].refund == 300, "two receipts must not double the sum"
        assert plans[wiped].refund == 0, "a player the July wipe already refunded is not refunded again"
        assert plans[whale].refund == 1200
        explained = await migration.explain(db, twice)
        assert explained["counted_refund"] == 300 and len(explained["sources"]["compensation_receipts"]) == 2
        old_cap = os.environ.get("SKINS_V3_REFUND_CAP"), os.environ.get("SKINS_V3_APPROVED_USERS")
        os.environ["SKINS_V3_REFUND_CAP"] = "1000"
        whale_before = await zarniki(db, whale)
        try:
            assert plans[whale].held and not plans[twice].held
            assert await migration.apply_user(db, plans[whale]) is False and await zarniki(db, whale) == whale_before, "a held refund changes nothing"
            async with db.execute("SELECT COUNT(*) FROM user_cosmetics WHERE user_id=?", (whale,)) as c:
                assert int((await c.fetchone())[0]) == 1, "a held player keeps their old items until approved"
            os.environ["SKINS_V3_APPROVED_USERS"] = str(whale)
            assert not plans[whale].held and await migration.apply_user(db, plans[whale]) is True and await zarniki(db, whale) == whale_before + 1200
        finally:
            for key, value in zip(("SKINS_V3_REFUND_CAP", "SKINS_V3_APPROVED_USERS"), old_cap):
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        print("OK: skins v3 buy/equip/upgrade/essence are idempotent; migration refunds exactly what was paid and archives the old system")
    finally:
        await outer.rollback()
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, default=os.getenv("DATABASE_URL", "postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod"))
    asyncio.run(run(parser.parse_args().dsn))
