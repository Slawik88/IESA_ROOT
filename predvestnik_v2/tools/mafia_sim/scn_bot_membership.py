"""Whole-bot scenarios: the bot being added to / removed from chats, members coming and going, the DM being blocked."""
from __future__ import annotations

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_util import OUTGOING, plain, said, say


def _sent_since(h: Harness, start: int) -> list[tuple[str, dict]]:
    return [(n, p) for n, p in h.world.calls[start:] if n in OUTGOING]


async def _chat_row(h: Harness, chat: int) -> dict | None:
    rows = await h.sql("SELECT bot_left_at IS NOT NULL AS left_chat, bot_is_admin, bot_can_moderate "
                       "FROM predvestnik.chat_settings WHERE chat_id=$1", chat)
    return dict(rows[0]) if rows else None


@bot_scenario
async def bot_added_as_admin_then_removed(h: Harness) -> None:
    owner = h.user("Владелец")
    chat = h.new_chat([owner])
    start = len(h.world.calls)
    await h.bot_membership(chat, owner, "left", "administrator", can_delete_messages=True, can_manage_chat=True,
                           can_restrict_members=True)
    texts = said(_sent_since(h, start))
    ok("Права получены" in texts and "Я администратор" in texts, f"the bot reports the rights it got: {texts[:160]!r}")
    ok("Спасибо, что добавили меня в чат" in texts, "and starts the setup checklist")
    row = await _chat_row(h, chat)
    ok(row == {"left_chat": False, "bot_is_admin": True, "bot_can_moderate": True}, f"chat state after adding: {row}")

    start = len(h.world.calls)
    await h.bot_membership(chat, owner, "administrator", "kicked")
    ok(not [1 for n, p in _sent_since(h, start) if int(p["chat_id"]) == chat], "a removed bot never writes into the chat it lost")
    row = await _chat_row(h, chat)
    ok(row == {"left_chat": True, "bot_is_admin": False, "bot_can_moderate": False}, f"chat state after removal: {row}")


@bot_scenario
async def bot_added_without_rights(h: Harness) -> None:
    owner = h.user("Владелец")
    chat = h.new_chat([owner])
    start = len(h.world.calls)
    await h.bot_membership(chat, owner, "left", "member")
    row = await _chat_row(h, chat)
    ok(row == {"left_chat": False, "bot_is_admin": False, "bot_can_moderate": False}, f"a plain member bot cannot moderate: {row}")
    ask = said([(n, p) for n, p in _sent_since(h, start) if int(p["chat_id"]) == chat])
    ok("мне нужны права администратора" in ask and "❌ Я администратор" in ask, f"a bot added without rights asks for them: {ask[:140]!r}")


@bot_scenario
async def member_join_and_leave(h: Harness) -> None:
    owner, guest = h.user("Владелец"), h.user("Гость")
    chat = h.new_chat([owner])
    await h.bot_membership(chat, owner, "left", "administrator", can_delete_messages=True, can_manage_chat=True, can_restrict_members=True)
    await h.member_change(chat, guest, owner, "left", "member")
    rows = await h.sql("SELECT is_left FROM predvestnik.user_chat_stats WHERE user_tg_id=$1 AND chat_tg_id=$2", guest.id, chat)
    ok(rows and rows[0]["is_left"] is False, f"a newcomer is recorded as present: {rows}")
    await h.member_change(chat, guest, owner, "member", "left")
    rows = await h.sql("SELECT is_left FROM predvestnik.user_chat_stats WHERE user_tg_id=$1 AND chat_tg_id=$2", guest.id, chat)
    ok(rows and rows[0]["is_left"] is True, f"and as left when they leave: {rows}")
    await h.member_change(chat, guest, owner, "left", "member")
    rows = await h.sql("SELECT is_left FROM predvestnik.user_chat_stats WHERE user_tg_id=$1 AND chat_tg_id=$2", guest.id, chat)
    ok(rows and rows[0]["is_left"] is False, f"a returning member is present again: {rows}")


@bot_scenario
async def dm_blocked_and_unblocked(h: Harness) -> None:
    player = h.user("Игрок")
    await say(h, player, h.new_chat([player]), "бот баланс")      # a player's record is created by their first message in a chat

    async def blocked() -> bool:
        rows = await h.sql("SELECT dm_blocked_at IS NOT NULL AS b FROM predvestnik.users WHERE user_tg_id=$1", player.id)
        return bool(rows and rows[0]["b"])

    ok(not await blocked(), "a new player is reachable")
    await h.blocked_by(player)
    ok(await blocked(), "blocking the bot marks the player as unreachable (broadcasts skip them)")
    h.world.dm_open.add(player.id)
    await h.bot_membership(player.id, player, "kicked", "member")      # the player unblocks the bot
    ok(not await blocked(), "unblocking makes the player reachable again")
