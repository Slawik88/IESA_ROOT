#!/usr/bin/env python3
"""PostgreSQL proof for whole-app skin ownership, selection and VIP fallback."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import global_skins_v1 as repo
from services import global_skins_v1 as skins


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await economy_ledger.ensure_tables(db)
    await repo.ensure_tables(db)
    transaction = connection.transaction()
    await transaction.start()
    try:
        user_id = 979201
        await db.execute("INSERT INTO users(user_tg_id,user_tg_username) VALUES (?,'skin_contract') ON CONFLICT DO NOTHING", (user_id,))
        initial = await skins.state(db, user_id)
        assert initial["selected_skin_id"] == initial["active_skin_id"] == "default"
        atlas = next(item for item in initial["items"] if item["id"] == "void_atlas")
        assert atlas["owned"] is False and atlas["price_zarniki"] == 1600
        assert atlas["lineup"] == "void" and atlas["asset"].endswith("void-atlas-v1.webp")
        try:
            await skins.select(db, user_id, "lunar_archive")
        except skins.SkinConflict:
            pass
        else:
            raise AssertionError("unowned skin selection must fail")
        try:
            await skins.select(db, user_id, "../../unknown")
        except skins.SkinConflict:
            pass
        else:
            raise AssertionError("unknown skin selection must fail")

        await repo.grant(db, user_id, "lunar_archive", source="contract_test")
        await repo.grant(db, user_id, "lunar_archive", source="contract_test")
        try:
            await repo.grant(db, user_id, "lunar_archive", source="conflicting_source")
        except ValueError:
            pass
        else:
            raise AssertionError("conflicting ownership provenance must fail")
        saved_without_vip = await skins.select(db, user_id, "lunar_archive")
        assert saved_without_vip["selected_skin_id"] == "lunar_archive"
        assert saved_without_vip["active_skin_id"] == "default"

        await db.execute(
            "INSERT INTO vip_subscriptions(user_id,tier,started_at,expires_at,expiry_notified,total_days) "
            "VALUES (?,'1m',NOW(),NOW()+INTERVAL '1 day',FALSE,1)",
            (user_id,),
        )
        active = await skins.state(db, user_id)
        assert active["active_skin_id"] == "lunar_archive"
        await db.execute("UPDATE vip_subscriptions SET expires_at=NOW()-INTERVAL '1 second' WHERE user_id=?", (user_id,))
        expired = await skins.state(db, user_id)
        assert expired["selected_skin_id"] == "lunar_archive" and expired["active_skin_id"] == "default"
        await db.execute("UPDATE vip_subscriptions SET expires_at=NOW()+INTERVAL '1 day' WHERE user_id=?", (user_id,))
        assert (await skins.state(db, user_id))["active_skin_id"] == "lunar_archive"

        buyer_id = 979202
        await db.execute(
            "INSERT INTO users(user_tg_id,user_tg_username,user_balance_zarniki) "
            "VALUES (?,'skin_buyer',2000) ON CONFLICT DO NOTHING",
            (buyer_id,),
        )
        message, bought = await skins.buy(
            db, buyer_id, "void_atlas", idempotency_key="global-skin:atlas-buy"
        )
        assert "1600" in message
        assert bought["selected_skin_id"] == "void_atlas"
        assert bought["active_skin_id"] == "void_atlas", "paid Atlas must activate without a hidden VIP paywall"
        async with db.execute(
            "SELECT user_balance_zarniki FROM users WHERE user_tg_id=?", (buyer_id,)
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 400
        replay_message, replay = await skins.buy(
            db, buyer_id, "void_atlas", idempotency_key="global-skin:atlas-buy"
        )
        assert "уже обработана" in replay_message and replay["selected_skin_id"] == "void_atlas"
        async with db.execute(
            "SELECT COUNT(*) FROM economic_operations WHERE user_id=? AND reason_code='global_skin_purchase'",
            (buyer_id,),
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 1

        poor_id = 979203
        await db.execute(
            "INSERT INTO users(user_tg_id,user_tg_username,user_balance_zarniki) "
            "VALUES (?,'skin_poor',1599) ON CONFLICT DO NOTHING",
            (poor_id,),
        )
        try:
            await skins.buy(db, poor_id, "void_atlas", idempotency_key="global-skin:poor")
        except skins.SkinConflict as error:
            assert "1600" in str(error)
        else:
            raise AssertionError("insufficient Zarniki must fail closed")
        assert "void_atlas" not in await repo.owned_ids(db, poor_id)
        async with db.execute(
            "SELECT user_balance_zarniki FROM users WHERE user_tg_id=?", (poor_id,)
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 1599
        async with db.execute(
            "SELECT COUNT(*) FROM economic_operations WHERE user_id=? AND reason_code='global_skin_purchase'",
            (poor_id,),
        ) as cursor:
            assert int((await cursor.fetchone())[0]) == 0

        await repo.set_selection(db, user_id, "removed_skin")
        stale = await skins.state(db, user_id)
        assert stale["selected_skin_id"] == stale["active_skin_id"] == "default"
        assert await repo.saved_selection(db, user_id) == "default"
        css = (ROOT / "FastAPI" / "static" / "global-skins-v1.css").read_text(encoding="utf-8")
        assert "animation" not in css and "lunar-archive-v1.webp" in css
        assert "void-atlas-v1.webp" in css and "body.skin-void-atlas" in css
        assert ".panel" in css and ".mine-panel" in css and ".mine-cell" in css
        client = (ROOT / "FastAPI" / "static" / "global-skins-v1.js").read_text(encoding="utf-8")
        assert "active_skin_id==='lunar_archive'" not in client
        assert "item&&item.active===true" in client and "active.css_class" in client
    finally:
        await transaction.rollback()
        await connection.close()


parser = argparse.ArgumentParser()
parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args()
asyncio.run(run(args.dsn))
print("Global skins v1: ownership, paid no-VIP activation, replay, insufficient-balance rollback and stale-selection safety OK")
