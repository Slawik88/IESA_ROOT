#!/usr/bin/env python3
"""«бот админ помощь» on the Telegram simulator (tools/mafia_sim): the real Dispatcher, fake Telegram, recorded outgoing calls (S09).

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_admin_help_sim_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod

- an ordinary member gets a pointer to the usual help, not the moderators' cheat sheet;
- a moderator (chat rank 4) sees this chat's thresholds with ✅ on what the rank allows, and no staff button;
- bot staff (role 2) gets the button «Справка администрации»: in the DM a Web App with ?open=guide, in a group a t.me link with startapp=admin_guide.
"""
from __future__ import annotations

import argparse
import asyncio
import os

MINIAPP = "https://miniapp.example/predvestnik/"


async def main(dsn: str) -> None:
    os.environ["DATABASE_URL"] = dsn
    os.environ["MINIAPP_URL"] = MINIAPP
    os.environ["MINIAPP_SHORT_NAME"] = "app"
    from tools.mafia_sim.harness import Harness, assert_dev_dsn
    from tools.mafia_sim.world import BOT_USERNAME
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from bot.chat import ranks

    assert_dev_dsn(dsn)
    harness = await Harness().open()
    world = harness.world
    member, moder, helper = harness.user("Участник"), harness.user("Модератор"), harness.user("Хелпер")
    group = harness.new_chat([member, moder, helper])
    try:
        for who in (member, moder, helper):
            await harness.say(who, group, "привет")   # бот узнаёт участников
        async with get_pool().acquire() as conn:
            db = PGAdapter(conn)
            await ranks.store_rank(db, group, moder.id, 4)
            await conn.execute("UPDATE users SET bot_rank = 2 WHERE user_tg_id = $1", helper.id)

        await harness.say(member, group, "бот админ помощь")
        reply = world.last(group, "Эта справка — для модераторов")
        assert reply is not None and not reply.buttons(), [m.text for m in world.live(group)][-2:]

        await harness.say(moder, group, "бот админ помощь")
        reply = world.last(group, "Админ-помощь · этот чат")
        assert reply is not None, [m.text for m in world.live(group)][-2:]
        assert "✅ Мут — с 🛡 Модератор (4)" in reply.text and "▫️ Бан — с 👮 Администратор (6)" in reply.text, reply.text
        assert not reply.buttons(), "модератору чата без роли в боте кнопка админки не нужна"

        await harness.say(helper, group, "бот админ помощь")
        reply = world.last(group, "Админ-помощь · этот чат")
        link = [b for b in reply.buttons() if "Справка администрации" in b.get("text", "")]
        assert link and link[0]["url"] == f"https://t.me/{BOT_USERNAME}/app?startapp=admin_guide" and "web_app" not in link[0], reply.buttons()

        await harness.say(helper, helper.id, "бот админ помощь")
        reply = world.last(helper.id, "Пороги по умолчанию")
        assert reply is not None, [m.text for m in world.live(helper.id)][-2:]
        button = [b for b in reply.buttons() if "Справка администрации" in b.get("text", "")]
        assert button and button[0]["web_app"]["url"].endswith("/bot-admin?open=guide"), reply.buttons()
    finally:
        async with get_pool().acquire() as conn:
            await conn.execute("UPDATE users SET bot_rank = 0 WHERE user_tg_id = $1", helper.id)
        await harness.close()
    print("OK: «бот админ помощь» — member pointer, moderator thresholds with ✅, staff button in group and DM (Telegram simulator)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dsn", required=True)
    asyncio.run(main(parser.parse_args().dsn))
