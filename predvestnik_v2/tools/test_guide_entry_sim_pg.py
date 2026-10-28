#!/usr/bin/env python3
"""The bot leads to the player guide (S07), on the Telegram simulator (tools/mafia_sim): the real Dispatcher, fake Telegram, recorded outgoing calls.

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_guide_entry_sim_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod

- «путеводитель» and /guide in the DM: a Web App button straight to the topic «Первый день» (?startapp=guide_first-day);
- «бот путеводитель» in a group: a t.me link to the Mini App with the same start parameter (Telegram forbids Web App buttons in groups);
- /start in the DM: the first screen has the button «📖 Путеводитель по игре»;
- «помощь» in the DM and «бот помощь» in a group name the guide.
"""
from __future__ import annotations

import argparse
import asyncio
import os

MINIAPP = "https://miniapp.example/predvestnik/"


async def main(dsn: str) -> None:
    os.environ["DATABASE_URL"] = dsn
    os.environ["MINIAPP_URL"] = MINIAPP              # read when the bot modules are imported
    os.environ["MINIAPP_SHORT_NAME"] = "app"
    from tools.mafia_sim.harness import Harness, assert_dev_dsn
    from tools.mafia_sim.world import BOT_USERNAME

    assert_dev_dsn(dsn)
    harness = await Harness().open()
    world = harness.world
    player = harness.user("Новичок")
    group = harness.new_chat([player])
    guide_url = f"{MINIAPP}?startapp=guide_first-day"

    def button(message, text):
        found = [b for b in message.buttons() if text in b.get("text", "")]
        assert found, (text, message.buttons())
        return found[0]

    try:
        for text in ("путеводитель", "/guide", "гайд"):
            await harness.say(player, player.id, text)
            reply = world.last(player.id, "Путеводитель по игре")
            assert reply is not None, [m.text for m in world.live(player.id)][-3:]
            assert button(reply, "Путеводитель")["web_app"]["url"] == guide_url, reply.buttons()
            reply.deleted = True

        await harness.say(player, group, "бот путеводитель")
        reply = world.last(group, "Путеводитель по игре")
        assert reply is not None, [m.text for m in world.live(group)][-3:]
        link = button(reply, "Путеводитель")
        assert "web_app" not in link and link["url"] == f"https://t.me/{BOT_USERNAME}/app?startapp=guide_first-day", link

        await harness.say(player, player.id, "/start")
        home = [m for m in world.live(player.id) if any("Путеводитель по игре" in b.get("text", "") for b in m.buttons())]
        assert home, "the first DM screen has the guide button"
        assert button(home[-1], "Путеводитель по игре")["web_app"]["url"] == guide_url

        await harness.say(player, player.id, "помощь")
        assert world.last(player.id, "Путеводителе: путеводитель") is not None, [m.text for m in world.live(player.id)][-2:]
        await harness.say(player, group, "бот помощь")
        assert world.last(group, "бот путеводитель") is not None, [m.text for m in world.live(group)][-2:]
    finally:
        await harness.close()
    print("OK: guide from the bot — DM button, /guide, group link, /start screen, help line (Telegram simulator)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dsn", required=True)
    asyncio.run(main(parser.parse_args().dsn))
