"""Whole-bot scenarios: inline buttons — double taps, buttons on deleted messages, foreign buttons, help menu."""
from __future__ import annotations

import asyncio

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_util import last_message, say, sim_friends
from tools.mafia_sim.world import StoredMessage


async def _seats(h: Harness, group: int) -> int:
    row = await h.match_row(group)
    if not row:
        return 0
    rows = await h.sql("SELECT count(*) AS n FROM predvestnik.mafia_v1_players WHERE match_id=$1", row["id"])
    return int(rows[0]["n"])


@bot_scenario
async def double_tap_join_is_idempotent(h: Harness) -> None:
    host, guest = h.user("Хозяин"), h.user("Гость")
    group = h.new_chat([host, guest])
    await say(h, host, group, "бот мафия")
    lobby = last_message(h, group, "набор игроков")
    before = await _seats(h, group)
    await h.click(guest, group, lobby, "Войти")
    await h.click(guest, group, lobby, "Войти")                     # an impatient second tap
    ok(await _seats(h, group) == before + 1, "two taps on «Войти» give exactly one seat")
    await h.click(guest, group, lobby, "Выйти")
    ok(await _seats(h, group) == before, "leaving removes the seat")


@bot_scenario(volatile=True)
async def parallel_taps_join_once(h: Harness) -> None:
    """A burst of simultaneous taps: the order of the answers is up to the scheduler, the outcome (one seat) is not."""
    host, guest = h.user("Хозяин"), h.user("Гость")
    group = h.new_chat([host, guest])
    await say(h, host, group, "бот мафия")
    lobby = last_message(h, group, "набор игроков")
    before = await _seats(h, group)
    await asyncio.gather(*(h.click(guest, group, lobby, "Войти") for _ in range(4)))
    ok(await _seats(h, group) == before + 1, "a burst of parallel taps gives exactly one seat")


@bot_scenario
async def help_menu_buttons(h: Harness) -> None:
    (player,), group = sim_friends(h, 1)
    await say(h, player, group, "бот помощь")
    menu = last_message(h, group, "Помощь")
    start = len(h.world.calls)
    click = await h.click(player, group, menu, "Профиль и валюта")
    ok(click.answered, "the section button is answered")
    section = last_message(h, group, "")
    ok("баланс" in section.text.lower() or "перевод" in section.text.lower(), f"the section lists its commands: {section.text[:90]!r}")
    ok(any(n == "EditMessageText" for n, _ in h.world.calls[start:]), "the menu is edited in place, not duplicated")


@bot_scenario
async def foreign_and_stale_buttons(h: Harness) -> None:
    owner, other = h.user("Хозяин"), h.user("Чужой")
    group = h.new_chat([owner, other])
    await say(h, owner, group, "бот помощь")
    menu = last_message(h, group, "Помощь")
    foreign = await h.click(other, group, menu, "Профиль и валюта")      # someone else's menu
    ok(foreign.answered, f"a foreign tap is answered (no endless spinner): {foreign}")
    menu.deleted = True
    stale = await h.click(owner, group, menu, "Профиль и валюта")          # the message is gone
    ok(stale.answered, f"a tap on a deleted message is answered too: {stale}")


@bot_scenario
async def unknown_callback_data_is_harmless(h: Harness) -> None:
    (player,), group = sim_friends(h, 1)
    await say(h, player, group, "бот помощь")
    menu = last_message(h, group, "Помощь")
    ghost = StoredMessage(group, menu.message_id, menu.text, {"inline_keyboard": [[{"text": "x", "callback_data": "retired:button:42"}]]})
    start = len(h.world.calls)
    await h.click(player, group, ghost, "x")
    ok(not [1 for n, _ in h.world.calls[start:] if n in ("SendMessage", "EditMessageText")], "an unknown button changes nothing")
