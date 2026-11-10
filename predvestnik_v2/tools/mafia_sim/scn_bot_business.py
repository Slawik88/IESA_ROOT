"""Whole-bot scenarios: Telegram Business — the updates route, and the bot in the player's own private chats (S24)."""
from __future__ import annotations

import copy

from aiogram.exceptions import TelegramBadRequest

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_util import OUTGOING, TemporaryHandlers, plain


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


# ── S24: the bot in the player's own private chats ──────────────────────────
#
# Who is who: ``owner`` connected the bot to his Telegram account; ``friend`` is the person he chats with. A message in that
# chat comes to the bot as a business_message with chat = the friend; the sender is either of them.

def biz_sent(h: Harness, since: int, connection_id: str) -> list[tuple[str, dict]]:
    """What the bot sent into the owner's chats on his behalf."""
    return [(n, p) for n, p in h.world.calls[since:] if n.startswith("Send") and p.get("business_connection_id") == connection_id]


def dm_to(h: Harness, user, since: int) -> list[str]:
    return [str(p.get("text")) for n, p in h.world.calls[since:]
            if n == "SendMessage" and int(p["chat_id"]) == user.id and p.get("business_connection_id") is None]


async def business_pair(h: Harness, tag: str, *, can_reply: bool = True):
    from tools.mafia_sim.scn_bot_dm_push import player
    owner = await player(h, f"Владелец {tag}")
    friend = await player(h, f"Друг {tag}")
    connection_id = f"bc-{tag}-{owner.id}"
    start = len(h.world.calls)
    await h.business_connect(owner, connection_id, can_reply=can_reply)
    return owner, friend, connection_id, start


async def stored(connection_id: str) -> dict:
    from tools.mafia_sim.scn_bot_dm_push import database
    async with database() as db:
        out = {}
        for table, column in (("business_connections", "id"), ("business_chats", "connection_id"), ("business_handled", "connection_id")):
            async with db.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (connection_id,)) as c:
                out[table] = int((await c.fetchone())[0])
    return out


@bot_scenario
async def business_chat_stays_silent_until_the_owner_turns_it_on(h: Harness) -> None:
    asked = set(h.dp.resolve_used_update_types())   # what start_polling(bot) asks Telegram for, with the real handlers only
    ok({"business_connection", "business_message"} <= asked, f"the bot asks Telegram for Business updates: {sorted(asked)}")
    ok(not {"edited_business_message", "deleted_business_messages"} & asked, "and not for edits and deletions it never needs")
    owner, friend, bc, connected = await business_pair(h, "silent")
    welcome = dm_to(h, owner, connected)
    ok(any("подключён к твоему аккаунту" in t and "бот вкл" in t for t in welcome), f"the owner gets a welcome in the DM: {welcome[-1:]}")
    start = len(h.world.calls)
    await h.business_say(bc, friend, friend, "бот кубик")                 # the friend tries a command
    await h.business_say(bc, owner, friend, "бот кубик")                  # the owner, but the chat is still off
    await h.business_say(bc, owner, friend, "пойдём гулять? бот подождёт")  # an ordinary message
    ok(not biz_sent(h, start, bc), "nothing is written into a chat where the owner did not turn the bot on")
    await h.business_say(bc, friend, friend, "бот вкл")                   # the friend cannot turn it on
    ok(not biz_sent(h, start, bc) and (await stored(bc))["business_chats"] == 0, "the friend cannot switch the bot on")
    start = len(h.world.calls)
    await h.business_say(bc, owner, friend, "бот вкл")
    turned = biz_sent(h, start, bc)
    ok([n for n, _ in turned] == ["SendMessage"] and "включён" in str(turned[0][1]["text"]), "«бот вкл» by the owner turns it on and says so in the chat")
    start = len(h.world.calls)
    await h.business_say(bc, owner, friend, "бот кубик")
    ok([n for n, _ in biz_sent(h, start, bc)] == ["SendDice"], "now the owner's dice is thrown in the chat")
    await h.business_say(bc, friend, friend, "бот кубик")
    ok(len(biz_sent(h, start, bc)) == 1, "the friend's command still does nothing")
    start = len(h.world.calls)
    await h.business_say(bc, owner, friend, "бот выбери чай или кофе или сок")
    picked = str(biz_sent(h, start, bc)[0][1]["text"]) if biz_sent(h, start, bc) else ""
    ok(any(w in picked for w in ("чай", "кофе", "сок")) and "Выбираю" in picked, f"«выбери» picks one of the options: {picked!r}")
    start = len(h.world.calls)
    await h.business_say(bc, owner, friend, "бот помощь")
    ok(not biz_sent(h, start, bc) and any("Бот в твоих переписках" in t for t in dm_to(h, owner, start)), "help goes to the owner's DM, not to the friend")
    start = len(h.world.calls)
    await h.business_say(bc, owner, friend, "бот выкл")
    await h.business_say(bc, owner, friend, "бот кубик")
    ok(not biz_sent(h, start, bc) and any("выключен" in t for t in dm_to(h, owner, start)), "after «бот выкл» the chat is silent again")


@bot_scenario
async def business_repeat_edit_delete_and_disconnect(h: Harness) -> None:
    owner, friend, bc, _ = await business_pair(h, "repeat")
    await h.business_say(bc, owner, friend, "бот вкл")
    message = h._business_message(bc, owner, friend, "бот кубик")
    start = len(h.world.calls)
    await h._feed({"business_message": message})
    await h._feed({"business_message": message})                         # Telegram delivers the same update again
    ok(len(biz_sent(h, start, bc)) == 1, "a repeated update throws the dice once")
    start = len(h.world.calls)
    await h.business_edit(bc, owner, friend, message["message_id"], "бот выбери да или нет")
    await h.business_delete(bc, friend, [message["message_id"]])
    ok(not biz_sent(h, start, bc), "editing or deleting a message does nothing")
    from tools.mafia_sim.scn_bot_dm_push import database
    async with database() as db:
        async with db.execute("SELECT column_name FROM information_schema.columns WHERE table_name LIKE 'business_%' "
                              "AND data_type IN ('text', 'character varying') AND column_name NOT IN ('id', 'connection_id')") as c:
            text_columns = [r[0] for r in await c.fetchall()]
    ok(not text_columns, f"no business table has a column for message text: {text_columns}")
    kept = await stored(bc)
    ok(kept["business_chats"] == 1 and kept["business_handled"] >= 1, f"only the switch and command numbers are kept: {kept}")
    start = len(h.world.calls)
    await h.business_connect(owner, bc, enabled=False)
    ok(await stored(bc) == {"business_connections": 0, "business_chats": 0, "business_handled": 0}, "disconnecting erases everything about the connection")
    ok(not [1 for n, _ in h.world.calls[start:] if n in OUTGOING], "and the bot says nothing about it")
    await h.business_say(bc, owner, friend, "бот кубик")
    ok(not biz_sent(h, start, bc), "a message from a dropped connection does nothing")


@bot_scenario
async def business_transfer_is_confirmed_only_in_the_owners_dm(h: Harness) -> None:
    from tools.mafia_sim.scn_bot_dm_push import database
    owner, friend, bc, _ = await business_pair(h, "money")
    stranger = h.user("Не играет")
    async with database() as db:
        await db.execute("UPDATE users SET user_balance_mora = 1000 WHERE user_tg_id = ?", (owner.id,))
        await db.execute("UPDATE users SET user_balance_mora = 0 WHERE user_tg_id = ?", (friend.id,))
        await db.commit()

    async def mora(user) -> int:
        async with database() as db:
            async with db.execute("SELECT COALESCE(user_balance_mora, 0) FROM users WHERE user_tg_id = ?", (user.id,)) as c:
                row = await c.fetchone()
        return int(row[0]) if row else 0

    await h.business_say(bc, owner, friend, "бот вкл")
    start = len(h.world.calls)
    await h.business_say(bc, friend, friend, "бот перевод 500")         # the friend asks for the owner's money
    ok(not dm_to(h, owner, start) and not biz_sent(h, start, bc), "the friend's «перевод» creates nothing")
    start = len(h.world.calls)
    await h.business_say(bc, owner, friend, "бот перевод 300")
    asks = [m for m in h.world.live(owner.id) if "Заявка из вашей переписки" in m.text]
    ok(asks and not biz_sent(h, start, bc), "the owner's request lands in his DM with the bot, not in the chat")
    ok(await mora(owner) == 1000, "nothing is taken before the owner confirms")
    request = asks[-1]
    stale = copy.deepcopy(request)                                        # the same buttons, as the second tap sees them
    foreign = await h.click(friend, owner.id, request, "Мора")
    ok(foreign.alert and await mora(owner) == 1000, f"someone else's tap is refused: {foreign.text!r}")
    await h.click(owner, owner.id, request, "Мора")
    await h.click(owner, owner.id, stale, "Мора")                        # a second tap on the same request
    ok(await mora(owner) == 700 and await mora(friend) == 300, f"300 Мора moved once: {await mora(owner)}/{await mora(friend)}")
    await h.business_say(bc, owner, stranger, "бот вкл")
    start = len(h.world.calls)
    await h.business_say(bc, owner, stranger, "бот перевод 10")
    ok(any("ещё не играет" in t for t in dm_to(h, owner, start)), "a person the bot does not know gets no transfer")


@bot_scenario
async def business_reply_rights_window_and_global_switch(h: Harness) -> None:
    from tools.mafia_sim.errors import TgError
    from tools.mafia_sim.scn_bot_dm_push import database
    owner, friend, bc, _ = await business_pair(h, "rights", can_reply=False)
    start = len(h.world.calls)
    await h.business_say(bc, owner, friend, "бот вкл")
    ok(any("право отвечать" in t for t in dm_to(h, owner, start)) and (await stored(bc))["business_chats"] == 0,
       "without the reply right the owner is told how to give it; the chat stays off")
    await h.business_connect(owner, bc, can_reply=True)                  # he gives the right
    await h.business_say(bc, owner, friend, "бот вкл")
    h.world.failures.append((lambda name, p: p.get("business_connection_id") == bc, TgError(400, "Bad Request: BUSINESS_PEER_INVALID"), [1]))
    start = len(h.world.calls)
    await h.business_say(bc, owner, friend, "бот совместимость")
    ok(any("последние сутки" in t for t in dm_to(h, owner, start)), "when Telegram refuses (24-hour window) the owner hears why in the DM")
    start = len(h.world.calls)
    await h.business_say(bc, owner, friend, "бот совместимость")
    sent = biz_sent(h, start, bc)
    ok(sent and "Совместимость" in str(sent[0][1]["text"]), f"compatibility with the friend: {sent[:1]}")
    async with database() as db:
        await db.execute("INSERT INTO bot_feature_switches (chat_id, feature, reason, updated_by) VALUES (0, 'group:business', 'тест', 0) "
                         "ON CONFLICT DO NOTHING")
        await db.commit()
    from services import feature_switches
    feature_switches.invalidate()
    try:
        start = len(h.world.calls)
        await h.business_say(bc, owner, friend, "бот кубик")
        ok(not biz_sent(h, start, bc) and not dm_to(h, owner, start), "«Бизнес-режим» off in «Функции»: the bot is silent everywhere")
    finally:
        async with database() as db:
            await db.execute("DELETE FROM bot_feature_switches WHERE chat_id = 0 AND feature = 'group:business'")
            await db.commit()
        feature_switches.invalidate()
    async with database() as db:   # «бот перевод» off in «Функции»: the transfer from a private chat is off too
        await db.execute("INSERT INTO bot_feature_switches (chat_id, feature, reason, updated_by) VALUES (0, 'cmd:перевод', 'тест', 0) "
                         "ON CONFLICT DO NOTHING")
        await db.commit()
    feature_switches.invalidate()
    try:
        start = len(h.world.calls)
        await h.business_say(bc, owner, friend, "бот перевод 5")
        ok(not [m for m in h.world.live(owner.id) if "Заявка из вашей переписки" in m.text] and any("отключены" in t for t in dm_to(h, owner, start)),
           "a switched-off transfer command creates no request")
    finally:
        async with database() as db:
            await db.execute("DELETE FROM bot_feature_switches WHERE chat_id = 0 AND feature = 'cmd:перевод'")
            await db.commit()
        feature_switches.invalidate()
    from services import global_moderation
    async with database() as db:   # a player blocked in the admin panel: the bot ignores him here as everywhere
        await db.execute("INSERT INTO bot_user_blocks (user_id, reason) VALUES (?, 'тест') ON CONFLICT DO NOTHING", (owner.id,))
        await db.commit()
    global_moderation.invalidate()
    try:
        start = len(h.world.calls)
        await h.business_say(bc, owner, friend, "бот кубик")
        ok(not biz_sent(h, start, bc) and not dm_to(h, owner, start), "a blocked player's commands are ignored")
    finally:
        async with database() as db:
            await db.execute("DELETE FROM bot_user_blocks WHERE user_id = ?", (owner.id,))
            await db.commit()
        global_moderation.invalidate()
    start = len(h.world.calls)
    await h.business_say(bc, owner, friend, "бот визитка")
    sent = biz_sent(h, start, bc)
    ok(sent and sent[0][0] in ("SendPhoto", "SendAnimation", "SendMessage"), f"the visiting card goes into the chat: {[n for n, _ in sent]}")
    shown = plain(sent[0][1])
    ok("Мора" not in shown and "Кошел" not in shown and "🆔" not in shown, f"the card shows no wallet and no id: {shown[:200]!r}")
    start = len(h.world.calls)
    await h.business_say(bc, owner, friend, "бот пригласить")
    ok(biz_sent(h, start, bc) and "t.me/" in str(biz_sent(h, start, bc)[0][1]["text"]), "the invitation carries the game link")


@bot_scenario
async def business_connection_made_before_the_release_is_picked_up(h: Harness) -> None:
    """A player connected the bot before S24 shipped: the bot never saw the connection update, Telegram still knows it."""
    from tools.mafia_sim.scn_bot_dm_push import player
    owner, friend = await player(h, "Подключил раньше"), await player(h, "Его друг")
    bc = f"bc-early-{owner.id}"
    h.world.add_business_connection(bc, owner.json(), enabled=True, can_reply=True)   # no update reached the bot
    await h.business_say(bc, owner, friend, "бот вкл")
    kept = await stored(bc)
    ok(kept["business_connections"] == 1 and kept["business_chats"] == 1, f"the bot asks Telegram and remembers it: {kept}")
    start = len(h.world.calls)
    await h.business_say(bc, friend, friend, "бот кубик")
    ok(not biz_sent(h, start, bc), "and still only the owner can command")
