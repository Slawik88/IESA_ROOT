#!/usr/bin/env python3
"""A failing bot handler reaches the health counters, on the Telegram simulator (tools/mafia_sim).

The simulator builds its Dispatcher with bot.dispatcher.build_dispatcher, exactly like production:

    BOT_TOKEN=1:x PYTHONPATH=. python tools/test_bot_error_monitor_sim_pg.py --dsn postgresql://predvestnik_preprod@127.0.0.1:5433/predvestnik_preprod
"""
from __future__ import annotations

import argparse
import asyncio
import os


async def main(dsn: str) -> None:
    os.environ["DATABASE_URL"] = dsn
    from aiogram import F

    from bot.chat import onboarding
    from core import ops_metrics
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from services import ops_health
    from tools.mafia_sim.harness import Harness, assert_dev_dsn

    assert_dev_dsn(dsn)
    harness = await Harness().open()
    ops_metrics.registry.drain()
    player = harness.user("Монитор")

    async def broken_dm_start(*_args, **_kwargs):
        raise LookupError("simulated failure inside a real handler")

    original = onboarding.dm_start
    onboarding.dm_start = broken_dm_start            # a real handler (/start in the DM) now fails deep inside
    try:
        try:
            await harness.say(player, player.id, "/start")
            raise AssertionError("the failure must still propagate as before")
        except LookupError:
            pass
    finally:
        onboarding.dm_start = original

    async def explode(message):
        raise ZeroDivisionError("text the player typed")
    harness.dp.message.register(explode, F.text == "сим авария")
    for _ in range(2):
        try:
            await harness.say(player, player.id, "сим авария")
        except ZeroDivisionError:
            pass

    counters = ops_metrics.registry.window.counters
    real = ("bot_error", "bot.chat.payments:cmd_start|LookupError")
    injected = ("bot_error", "tools.test_bot_error_monitor_sim_pg:explode|ZeroDivisionError")
    assert counters.get(real) == 1, counters
    assert counters.get(injected) == 2, counters

    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        panel = await ops_health.dashboard(db, 1)
        top = {(row["handler"], row["exc"]): row["count"] for row in panel["bot_errors"]["top"]}
        assert top.get(("bot.chat.payments:cmd_start", "LookupError")) == 1, top
        assert top.get(("tools.test_bot_error_monitor_sim_pg:explode", "ZeroDivisionError")) == 2, top
        stored = await conn.fetch(
            "SELECT handler, update_type, exc_type, trace FROM bot_handler_errors "
            "WHERE handler IN ('bot.chat.payments:cmd_start', 'tools.test_bot_error_monitor_sim_pg:explode')")
        assert len(stored) == 2, stored                 # one stored example per handler and type a minute
        assert all(r["update_type"] == "message" for r in stored)
        assert all("player" not in r["trace"] and str(player.id) not in r["trace"] for r in stored)
        assert any("bot/chat/payments.py" in r["trace"] for r in stored)
        await conn.execute(
            "DELETE FROM bot_handler_errors WHERE handler IN ('bot.chat.payments:cmd_start', 'tools.test_bot_error_monitor_sim_pg:explode')")
    ops_metrics.registry.drain()
    await harness.close()
    print("OK: bot handler errors are counted per handler on the Telegram simulator")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    asyncio.run(main(parser.parse_args().dsn))
