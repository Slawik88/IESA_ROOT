"""Whole-bot scenarios: Telegram Business — the updates arrive, parse and route (the bot has no Business features yet)."""
from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_util import OUTGOING, TemporaryHandlers


@bot_scenario
async def business_updates_are_routed(h: Harness) -> None:
    owner, friend = h.user("Владелец"), h.user("Друг")
    seen: list[tuple] = []

    async def on_connection(c): seen.append(("connection", c.id, c.is_enabled, c.user.id))
    async def on_message(m): seen.append(("message", m.business_connection_id, m.text, m.from_user.id))
    async def on_edit(m): seen.append(("edited", m.business_connection_id, m.text))
    async def on_delete(d): seen.append(("deleted", d.business_connection_id, tuple(d.message_ids)))

    with TemporaryHandlers(h.dp):
        h.dp.business_connection.register(on_connection)
        h.dp.business_message.register(on_message)
        h.dp.edited_business_message.register(on_edit)
        h.dp.deleted_business_messages.register(on_delete)
        start = len(h.world.calls)
        await h.business_connect(owner, "bc-route", can_reply=True)
        first = await h.business_say("bc-route", friend, friend, "привет из личной переписки")
        await h.business_edit("bc-route", friend, friend, first, "привет (исправлено)")
        await h.business_delete("bc-route", friend, [first])
        await h.business_connect(owner, "bc-route", enabled=False)
        asked = sorted(h.dp.resolve_used_update_types())
    kinds = [row[0] for row in seen]
    ok(kinds == ["connection", "message", "edited", "deleted", "connection"], f"all five Business updates reach their handlers: {seen}")
    ok(seen[1] == ("message", "bc-route", "привет из личной переписки", friend.id), seen[1])
    ok(seen[4][2] is False, "the second connection update says the account disconnected the bot")
    ok(not [1 for n, _ in h.world.calls[start:] if n in OUTGOING], "and none of it makes the bot write anything on its own")
    ok({"business_connection", "business_message", "edited_business_message", "deleted_business_messages"} <= set(asked),
       f"a bot that handles Business is asked for those updates: {asked}")


@bot_scenario
async def business_connection_rules(h: Harness) -> None:
    owner, friend = h.user("Владелец"), h.user("Друг")
    await h.business_connect(owner, "bc-rules", can_reply=True)
    connection = await h.bot.get_business_connection("bc-rules")
    ok(connection.id == "bc-rules" and connection.is_enabled and connection.user.id == owner.id, f"{connection}")
    ok(connection.rights and connection.rights.can_reply, "the bot may reply on the owner's behalf")
    sent = await h.bot.send_message(friend.id, "ответ от имени владельца", business_connection_id="bc-rules")
    ok(sent.message_id, "a business reply is accepted by Telegram")
    await h.business_connect(owner, "bc-readonly", can_reply=False)
    for connection_id, label in (("bc-readonly", "a connection without the reply right"), ("no-such-connection", "an unknown connection")):
        try:
            await h.bot.send_message(friend.id, "x", business_connection_id=connection_id)
            raise AssertionError(f"{label} must be refused")
        except TelegramBadRequest:
            pass
    await h.business_connect(owner, "bc-rules", enabled=False)
    try:
        await h.bot.send_message(friend.id, "x", business_connection_id="bc-rules")
        raise AssertionError("a disconnected account must be refused")
    except TelegramBadRequest:
        pass
