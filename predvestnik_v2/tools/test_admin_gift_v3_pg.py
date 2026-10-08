#!/usr/bin/env python3
"""PostgreSQL proof: what the console gives (personal skin, regalia, VIP) is stored as an admin gift for an offline player, and taking away gifts nothing."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from unittest import mock
from urllib.parse import urlparse

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from FastAPI.routers.dev_console import marks as marks_router  # noqa: E402
from FastAPI.routers.dev_console import skins as skins_router  # noqa: E402
from FastAPI.routers.dev_console import vip as vip_router  # noqa: E402
from infrastructure.pg_adapter import PGAdapter  # noqa: E402
from infrastructure.repositories import admin_log, marks_v1 as marks_repo, skins_v3 as skins_repo, web_notifications  # noqa: E402


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await admin_log.ensure_table(db)
    await web_notifications.ensure_table(db)
    await skins_repo.ensure_tables(db)
    await marks_repo.ensure_tables(db)
    outer = connection.transaction()
    await outer.start()
    try:
        admin, player = 984001, 984002
        for uid in (admin, player):
            await db.execute("INSERT INTO users(user_tg_id,user_tg_username) VALUES (?,?) ON CONFLICT (user_tg_id) DO NOTHING", (uid, f"g{uid}"))
        me = {"id": admin}
        await db.execute("DELETE FROM skins_v3_owned WHERE skin_id IN ('scarlet_star','crimson_dark')")      # a local database may hold them from manual runs; the rollback restores it

        async def unseen() -> list[dict]:
            got = await web_notifications.get_unseen(db, player)
            await web_notifications.mark_seen(db, player, [g["id"] for g in got])
            return [g["payload"] for g in got]

        with mock.patch.object(skins_router, "require_console_perm", mock.AsyncMock()), mock.patch.object(marks_router, "require_console_perm", mock.AsyncMock()), \
                mock.patch.object(vip_router, "require_console_perm", mock.AsyncMock()), mock.patch.object(vip_router, "_tg_call", mock.AsyncMock()), \
                mock.patch("FastAPI.notifications.notify", mock.AsyncMock(return_value=False)):       # the player is offline: the gift waits in web_notifications
            # personal skin: given at tier D, the gift names it and carries the id the card validates
            out = await skins_router.dev_skins_grant(skins_router.SkinGiftRequest(user_id=player, skin_id="scarlet_star", reason="вклад в проект"), db, me)
            assert out["ok"] and "тир D" in out["message"]
            payloads = await unseen()
            assert len(payloads) == 1 and payloads[0]["type"] == "admin_gift" and payloads[0]["reason"] == "вклад в проект", payloads
            gift = payloads[0]["gifts"][0]
            assert gift["kind"] == "skin" and gift["skin_id"] == "scarlet_star" and "Алая Звезда" in gift["label"], gift
            assert (await skins_repo.owned(db, player)) == {"scarlet_star": "D"}
            # taking it back gifts nothing and is journaled
            await skins_router.dev_skins_revoke(skins_router.SkinGiftRequest(user_id=player, skin_id="scarlet_star", reason="ошиблись"), db, me)
            assert await unseen() == [] and await skins_repo.owned(db, player) == {}
            async with db.execute("SELECT action, detail FROM admin_grant_log WHERE target_id=? ORDER BY id", (player,)) as c:
                assert [tuple(r) for r in await c.fetchall()] == [("skin", "+ Алая Звезда"), ("skin", "- Алая Звезда")]
            # regalia
            await marks_router.dev_marks_grant(marks_router.MarkRequest(user_id=player, mark_id="founder", reason="с первого дня"), db, me)
            payloads = await unseen()
            assert payloads[0]["gifts"][0]["kind"] == "mark" and "Первопроходец" in payloads[0]["gifts"][0]["label"] and payloads[0]["gifts"][0]["glyph"] == "🧭", payloads
            await marks_router.dev_marks_revoke(marks_router.MarkRequest(user_id=player, mark_id="founder", reason="ошибка"), db, me)
            assert await unseen() == []
            # VIP: grant and extension gift days, shortening does not
            await vip_router.dev_give_vip(vip_router.GiveVipRequest(user_id=player, tier="1m", days=30), db, me)
            payloads = await unseen()
            assert payloads[0]["gifts"][0]["kind"] == "vip" and payloads[0]["gifts"][0]["amount"] == 30 and payloads[0]["gifts"][0]["unit"] == "дн.", payloads
            await vip_router.dev_adjust_vip_days(vip_router.AdjustVipRequest(user_id=player, days=7), db, me)
            assert (await unseen())[0]["gifts"][0]["amount"] == 7
            await vip_router.dev_adjust_vip_days(vip_router.AdjustVipRequest(user_id=player, days=-5), db, me)
            assert await unseen() == []
        print("OK: admin gifts for a personal skin, regalia and VIP reach an offline player; taking away gifts nothing")
    finally:
        await outer.rollback()
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", type=local_dsn, default=os.getenv("DATABASE_URL", "postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod"))
    asyncio.run(run(parser.parse_args().dsn))
