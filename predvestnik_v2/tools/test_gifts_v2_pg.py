#!/usr/bin/env python3
"""Real PostgreSQL proof for ECO-04 PR-C gifts: send to the partner, limits on the UTC day, shelf pins and the public card."""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import pathlib
import sys
import time
from urllib.parse import urlparse

import asyncpg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core import gifts_v2 as policy
from core import shop_v1 as shop_policy
from FastAPI.routers import gifts_v2 as router
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import gifts_v2 as repo
from infrastructure.repositories import public_profiles_v1 as public_profiles
from infrastructure.repositories import shop_v1 as shop_repo
from infrastructure.repositories import skins_v3 as essence_repo
from infrastructure.repositories import system_flags
from infrastructure.repositories import zarniki_exchange_v1 as exchange_repo
from infrastructure.repositories.marriages import create_marriage, delete_marriage
from services import gifts_v2 as gifts
from services import shop_v1 as shop


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def scalar(db, sql: str, params: tuple = ()):
    async with db.execute(sql, params) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else None


async def fund(db, user: int, *, mora=0, diamonds=0, zarniki=0) -> None:
    await db.execute(
        "INSERT INTO users(user_tg_id,user_tg_username,user_balance_mora,user_balance_diamonds,user_balance_zarniki) "
        "VALUES (?,?,?,?,?) ON CONFLICT(user_tg_id) DO UPDATE SET user_balance_mora=EXCLUDED.user_balance_mora,"
        "user_balance_diamonds=EXCLUDED.user_balance_diamonds,user_balance_zarniki=EXCLUDED.user_balance_zarniki",
        (user, f"giftuser{user % 1000}", mora, diamonds, zarniki),
    )


async def wallet(db, user: int) -> tuple:
    async with db.execute(
        "SELECT user_balance_mora,user_balance_diamonds,user_balance_zarniki FROM users WHERE user_tg_id=?", (user,),
    ) as cursor:
        row = await cursor.fetchone()
    return float(row[0]), float(row[1]), float(row[2])


def cat() -> dict:
    return dict(catalog_version=policy.GIFTS_VERSION, catalog_digest=policy.catalog_digest())


async def send(db, user: int, gift: str, action: str, note=None, to=None) -> dict:
    return await gifts.send(db, sender_id=user, gift_id=gift, action_id=action, note=note, to_ref=to, **cat())


async def refused(coro, text: str = "", kind=gifts.GiftConflict) -> str:
    try:
        await coro
    except kind as exc:
        assert text in str(exc), (text, str(exc))
        return str(exc)
    raise AssertionError(f"expected a refusal: {text}")


async def nothing_happened(db, user: int, before: tuple) -> None:
    assert await wallet(db, user) == before
    assert await scalar(db, "SELECT COUNT(*) FROM gift_sends_v2 WHERE sender_id=?", (user,)) == 0


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    tx = connection.transaction()
    await tx.start()
    real_window, real_dm = repo.window, gifts._bot_dm
    dms: list = []

    async def fake_dm(user_id, text):
        dms.append((user_id, text))

    gifts._bot_dm = fake_dm
    try:
        db = PGAdapter(connection)
        await system_flags.ensure_table(db)
        await essence_repo.ensure_tables(db)
        await exchange_repo.ensure_tables(db)
        await shop_repo.ensure_tables(db)
        await repo.ensure_tables(db)
        await system_flags.set_flag(db, policy.FLAG, False)
        alice, bob, carol, dave, solo = 996_000_001, 996_000_002, 996_000_003, 996_000_004, 996_000_005
        for user in (alice, bob, carol, dave, solo):
            await fund(db, user, mora=100_000, diamonds=100, zarniki=10_000)
        await create_marriage(db, 0, alice, "A", bob, "B")
        refs = await public_profiles.ensure_references(db, [alice, bob, carol, dave, solo])

        # Flag off: no screen, no gift, no gifts block on the public card; old partner gifts are untouched.
        await refused(gifts.overview(db, user_id=alice), "закрыты", gifts.GiftsClosed)
        await refused(send(db, alice, "gift_rose", "off-1"), "закрыты", gifts.GiftsClosed)
        await refused(gifts.history(db, user_id=alice, box="received"), "закрыты", gifts.GiftsClosed)
        assert await gifts.public_view(db, target_id=bob, viewer_id=alice) is None
        await nothing_happened(db, alice, (100_000, 100, 10_000))
        await system_flags.set_flag(db, policy.FLAG, True)

        # Not married, self, a stranger: refused before any debit.
        await refused(send(db, solo, "gift_rose", "solo-1"), gifts.NOT_MARRIED)
        await refused(send(db, alice, "gift_rose", "self-1", to=refs[alice]), gifts.SELF)
        await refused(send(db, alice, "gift_rose", "stranger-1", to=refs[carol]), gifts.NOT_MARRIED)
        await refused(send(db, alice, "gift_rose", "nobody-1", to="x" * 20), "не найден")
        await nothing_happened(db, solo, (100_000, 100, 10_000))
        await nothing_happened(db, alice, (100_000, 100, 10_000))
        view = await gifts.overview(db, user_id=solo)
        assert view["recipient"] is None and view["unavailable_reason"] == gifts.NOT_MARRIED
        assert not any(g["available"] for t in view["tiers"] for g in t["gifts"])

        # Shortages per currency (Mora, 💎, ✨): named, nothing debited.
        await create_marriage(db, 0, carol, "C", dave, "D")
        for gift_id, wallet_args, text in (("gift_bouquet", dict(mora=1_000), "Не хватает: 500 🪙."),
                                           ("gift_ring", dict(diamonds=5.5), "Не хватает: 1 💎."),
                                           ("gift_constellation", dict(zarniki=10), "Не хватает: 2990 ✨.")):
            await fund(db, carol, **wallet_args)
            before = await wallet(db, carol)
            assert await refused(send(db, carol, gift_id, f"poor-{gift_id}")) == text
            await nothing_happened(db, carol, before)
        items = {g["id"]: g for t in (await gifts.overview(db, user_id=carol))["tiers"] for g in t["gifts"]}
        assert items["gift_constellation"]["missing"] == {"zarniki": 2990} and items["gift_card"]["affordable"] is False
        assert items["gift_crown"]["irreversible"] is True and items["gift_card"]["irreversible"] is False

        # Note validation: too long or control characters are refused without a debit.
        await refused(send(db, alice, "gift_rose", "note-long", note="x" * 61), "60")
        await refused(send(db, alice, "gift_rose", "note-ctl", note="hi‮"), "служебные")
        await nothing_happened(db, alice, (100_000, 100, 10_000))

        # Fixed UTC window: Monday 2026-10-12.
        day1 = dt.date(2026, 10, 12)
        windows = {"now": (day1, day1, dt.datetime(2026, 10, 12, 23, 0, 0))}

        async def fixed_window(_db):
            return windows["now"]

        repo.window = fixed_window
        first = await send(db, alice, "gift_crown", "a-1", note="  <b>Люблю</b> & 🌹 ")
        assert first["applied"] and first["tier"] == 4 and first["note"] == "<b>Люблю</b> & 🌹" and first["sent_on"] == "2026-10-12"
        assert first["price"] == {"zarniki": 800} and first["receiver_id"] == bob
        assert await wallet(db, alice) == (100_000, 100, 9_200)
        assert await scalar(db, "SELECT reason_code FROM economic_operations WHERE id=?",
                            (first["economy_operation_id"],)) == policy.REASON_CODE
        row = await repo.get_send(db, first["send_id"])
        assert (row["sender_id"], row["receiver_id"], row["gift_id"], row["tier"]) == (alice, bob, "gift_crown", 4)

        # Replay: same receipt, no second debit, even with a stale catalogue; another gift or note -> 409.
        again = await gifts.send(db, sender_id=alice, gift_id="gift_crown", action_id="a-1", note="<b>Люблю</b> & 🌹",
                                 catalog_version="old", catalog_digest="0" * 64)
        assert again["send_id"] == first["send_id"] and again["applied"] is False and await wallet(db, alice) == (100_000, 100, 9_200)
        await refused(send(db, alice, "gift_rose", "a-1"), "action_id")
        await refused(send(db, alice, "gift_crown", "a-1", note="другая"), "action_id")
        await refused(gifts.send(db, sender_id=alice, gift_id="gift_rose", action_id="a-stale",
                                 catalog_version=policy.GIFTS_VERSION, catalog_digest="0" * 64), "Каталог")

        # One action id belongs to one store: gift ids are refused by the shop and shop ids by gifts.
        await system_flags.set_flag(db, shop_policy.FLAG, True)
        await refused(shop.buy(db, user_id=alice, item_id="ess_polish", action_id="a-1",
                               catalog_version=shop_policy.SHOP_VERSION, catalog_digest=shop_policy.catalog_digest()),
                      "action_id", shop.ShopConflict)
        polish = await shop.buy(db, user_id=alice, item_id="ess_polish", action_id="shop-1",
                                catalog_version=shop_policy.SHOP_VERSION, catalog_digest=shop_policy.catalog_digest())
        assert polish["receipt"]["applied"]
        await refused(send(db, alice, "gift_rose", "shop-1"), "action_id")
        assert await shop_repo.action_owner(db, user_id=alice, action_id="a-1") == "gift"
        mora_after_polish = (await wallet(db, alice))[0]

        # 3 a day to one recipient.
        assert (await send(db, alice, "gift_rose", "a-2"))["applied"]
        assert (await send(db, alice, "gift_card", "a-3"))["applied"]
        before = await wallet(db, alice)
        await refused(send(db, alice, "gift_card", "a-4"), "одному игроку")
        assert await wallet(db, alice) == before
        view = await gifts.overview(db, user_id=alice)
        assert view["limits"]["recipient"] == {"max": 3, "used": 3, "left": 0} and view["limits"]["daily"]["left"] == 2
        assert view["limits"]["resets_in_seconds"] == 3600 and view["recipient"]["ref"] == refs[bob]
        assert "user_tg_id" not in str(view) and str(bob) not in str(view)

        # 5 a day in total: a new partner the same UTC day gets two more, the sixth is refused.
        assert await delete_marriage(db, alice)
        await refused(send(db, alice, "gift_card", "a-5"), gifts.NOT_MARRIED)
        await create_marriage(db, 0, alice, "A", solo, "S")
        assert (await send(db, alice, "gift_card", "a-6"))["receiver_id"] == solo
        assert (await send(db, alice, "gift_card", "a-7"))["applied"]
        await refused(send(db, alice, "gift_card", "a-8"), "5 подарков в сутки")
        assert await scalar(db, "SELECT COUNT(*) FROM gift_sends_v2 WHERE sender_id=? AND sent_on=?", (alice, day1)) == 5
        assert (await wallet(db, alice))[0] == mora_after_polish - 300 - 150 * 3

        # Next UTC day: limits reset.
        windows["now"] = (day1 + dt.timedelta(days=1), day1, dt.datetime(2026, 10, 13, 0, 0, 1))
        assert (await send(db, alice, "gift_star", "a-9"))["sent_on"] == "2026-10-13"
        assert (await gifts.overview(db, user_id=alice))["limits"]["daily"] == {"max": 5, "used": 1, "left": 4}

        # Append-only receipts.
        for sql in ("UPDATE gift_sends_v2 SET note='x' WHERE id=?", "DELETE FROM gift_sends_v2 WHERE id=?"):
            try:
                async with connection.transaction():   # savepoint: the refused write rolls back alone
                    await db.execute(sql, (first["send_id"],))
            except asyncpg.PostgresError as exc:
                assert "append-only" in str(exc)
            else:
                raise AssertionError("receipts must be append-only")

        # Shelf: bob received crown, rose, card. Counters, slots, history filter.
        shelf = await gifts.shelf(db, user_id=bob)
        assert shelf["counts"] == {"received": 3, "sent": 0}
        slots = {s["gift_id"]: s["count"] for t in shelf["tiers"] for s in t["slots"]}
        assert len(slots) == 12 and slots["gift_crown"] == 1 and slots["gift_rose"] == 1 and slots["gift_bear"] == 0
        assert shelf["top_badge"]["icon"] == "👑" and shelf["pinned"] == []
        assert (await gifts.shelf(db, user_id=alice))["counts"] == {"received": 0, "sent": 6}
        hist = await gifts.history(db, user_id=bob, box="received", tier=4)
        assert [h["gift_id"] for h in hist["items"]] == ["gift_crown"] and hist["items"][0]["note"] == "<b>Люблю</b> & 🌹"
        assert hist["items"][0]["from"]["ref"] == refs[alice] and "price" not in hist["items"][0]
        sent = await gifts.history(db, user_id=alice, box="sent")
        assert len(sent["items"]) == 6 and sent["items"][0]["price"] and {h["to"]["ref"] for h in sent["items"]} == {refs[bob], refs[solo]}
        assert len((await gifts.history(db, user_id=bob, box="received", gift_id="gift_rose"))["items"]) == 1
        await refused(gifts.history(db, user_id=bob, box="all"), "received")

        # Pins: only own received gifts, at most 3, unpin frees a place.
        received = [h["id"] for h in (await gifts.history(db, user_id=bob, box="received"))["items"]]
        await refused(gifts.set_pin(db, user_id=alice, send_id=received[0], pinned=True), "только подарок")
        await refused(gifts.set_pin(db, user_id=bob, send_id="f" * 32, pinned=True), "только подарок")
        for send_id in received:
            await gifts.set_pin(db, user_id=bob, send_id=send_id, pinned=True)
        await gifts.set_pin(db, user_id=bob, send_id=received[0], pinned=True)  # idempotent
        windows["now"] = (day1 + dt.timedelta(days=1), day1, dt.datetime(2026, 10, 13, 1, 0, 0))
        await delete_marriage(db, alice)
        await create_marriage(db, 0, alice, "A", bob, "B")
        fourth = await send(db, alice, "gift_bear", "a-10")
        await refused(gifts.set_pin(db, user_id=bob, send_id=fourth["send_id"], pinned=True), "не больше 3")
        await gifts.set_pin(db, user_id=bob, send_id=received[1], pinned=False)
        result = await gifts.set_pin(db, user_id=bob, send_id=fourth["send_id"], pinned=True)
        assert len(result["shelf"]["pinned"]) == 3 and fourth["send_id"] in {p["id"] for p in result["shelf"]["pinned"]}
        assert await scalar(db, "SELECT COUNT(*) FROM gift_pins_v2 WHERE receiver_id=?", (bob,)) == 3

        # Public card: pinned (max 3) + total + badge only; no notes, no senders; can_send only for the partner.
        public = await gifts.public_view(db, target_id=bob, viewer_id=carol)
        assert public["total"] == 4 and len(public["pinned"]) == 3 and public["can_send"] is False
        assert public["top_badge"]["icon"] == "👑" and "note" not in str(public) and "Люблю" not in str(public)
        assert set(public["pinned"][0]) == {"gift_id", "name", "icon", "tier", "tier_name"}
        assert (await gifts.public_view(db, target_id=bob, viewer_id=alice))["can_send"] is True
        assert (await gifts.public_view(db, target_id=bob, viewer_id=bob))["can_send"] is False
        empty = await gifts.public_view(db, target_id=carol, viewer_id=bob)
        assert empty == {"total": 0, "pinned": [], "top_badge": None, "can_send": False}

        # The router: a failing notification never undoes a committed gift; the response hides Telegram ids.
        dms.clear()
        body = router.SendRequest(gift_id="gift_choco", action_id="a-11", note="Привет <i>", **cat())
        ok = await router.send(body, db=db, user={"id": alice})
        assert ok["ok"] and "receiver_id" not in ok["receipt"] and ok["balances"]["mora"] == (await wallet(db, alice))[0]
        assert dms and dms[0][0] == bob and "&lt;i&gt;" in dms[0][1] and "<i>" not in dms[0][1]

        async def broken(*_args, **_kwargs):
            raise RuntimeError("telegram is down")

        gifts._bot_dm = broken
        body = router.SendRequest(gift_id="gift_choco", action_id="a-12", **cat())
        assert (await router.send(body, db=db, user={"id": alice}))["receipt"]["applied"]
        real_notify = gifts.notify_recipient
        gifts.notify_recipient = broken
        try:
            body = router.SendRequest(gift_id="gift_card", action_id="a-13", **cat())
            await refused(router.send(body, db=db, user={"id": alice}), "", router.HTTPException)  # 3 a day to bob
            windows["now"] = (day1 + dt.timedelta(days=2), day1, dt.datetime(2026, 10, 14, 1, 0, 0))
            assert (await router.send(body, db=db, user={"id": alice}))["receipt"]["applied"]
        finally:
            gifts.notify_recipient = real_notify
        assert await repo.find_send(db, sender_id=alice, action_id="a-13")

        # Flag off again: new gifts refused, a replay still returns its receipt.
        await system_flags.set_flag(db, policy.FLAG, False)
        await refused(send(db, alice, "gift_card", "a-off"), "закрыты", gifts.GiftsClosed)
        assert (await send(db, alice, "gift_crown", "a-1", note="<b>Люблю</b> & 🌹"))["send_id"] == first["send_id"]
        assert await gifts.public_view(db, target_id=bob, viewer_id=carol) is None
    finally:
        repo.window, gifts._bot_dm = real_window, real_dm
        await tx.rollback()
        await connection.close()

    await race(dsn)
    print("OK: gifts — flag gate, partner only (not married/self/stranger refused), shortages per currency debit nothing, "
          "replay = same receipt, other gift/note same id → 409, one action id per store, 5/day and 3/recipient/day on a fixed UTC day, "
          "notes ≤60 plain text, append-only receipts, pins ≤3 own only, public card = pinned + total, notify failure keeps the gift, 16×30 race")


async def race(dsn: str) -> None:
    """Pool of 16 connections, 30 sends from one player to the partner: never more than 3 a day to one recipient."""
    base = 997_000_000 + (time.time_ns() // 1000) % 900_000 * 2
    sender, partner = base, base + 1
    setup = await asyncpg.connect(dsn)
    sdb = PGAdapter(setup)
    await system_flags.ensure_table(sdb)
    flag_before = await system_flags.is_enabled(sdb, policy.FLAG)
    real_dm = gifts._bot_dm
    try:
        await repo.ensure_tables(sdb)
        await system_flags.set_flag(sdb, policy.FLAG, True)
        await fund(sdb, sender, mora=100_000)
        await fund(sdb, partner)
        await create_marriage(sdb, 0, sender, "S", partner, "P")
        pool = await asyncpg.create_pool(dsn, min_size=16, max_size=16)
        try:
            async def task(index: int):
                async with pool.acquire() as conn:
                    db = PGAdapter(conn)
                    try:
                        return await send(db, sender, "gift_bear", f"race-gift-{index % 25}")
                    except gifts.GiftConflict:
                        return None

            results = await asyncio.gather(*(task(index) for index in range(30)))
        finally:
            await pool.close()
        applied = [r for r in results if r and r["applied"]]
        assert len(applied) == 3, len(applied)
        assert await scalar(sdb, "SELECT MAX(n) FROM (SELECT COUNT(*) n FROM gift_sends_v2 WHERE sender_id=? GROUP BY sent_on) x",
                            (sender,)) == 3
        assert (await wallet(sdb, sender))[0] == 100_000 - 3 * 800
        assert await scalar(sdb, "SELECT COUNT(*) FROM economic_operations WHERE user_id=? AND reason_code=?",
                            (sender, policy.REASON_CODE)) == 3
    finally:
        gifts._bot_dm = real_dm
        await delete_marriage(sdb, sender)
        await system_flags.set_flag(sdb, policy.FLAG, flag_before)
        await setup.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
