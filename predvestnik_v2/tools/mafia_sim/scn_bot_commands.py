"""Whole-bot scenarios: the everyday commands, in a DM («баланс») and in a group («бот баланс»)."""
from __future__ import annotations

import dataclasses
import re

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_util import last_message, said, say, sim_friends

# command → a phrase every reply must contain.  Pets, star dust and the site are switched off in a clean database,
# and the bot says so politely: that answer is part of the contract too.
DM_COMMANDS = {
    "баланс": "Баланс", "топ": "Топ всех игроков", "я": "Кошелёк", "кто я": "Кошелёк", "вип": "VIP не активен",
    "стрик": "Ваш стрик", "достижения": "Ваши достижения", "семья": "нет семьи",
    "помощь": "Помощь", "ритм": "РИТМ", "промокод": "Формат команды", "питомцы": "недоступны",
    "купить зарники": "ЗАРНИКИ", "сайт": "Нажмите кнопку", "звездопад": "недоступен", "пыль": "недоступна",
}
GROUP_COMMANDS = {
    "бот баланс": "Баланс", "бот топ": "Топ чата", "бот я": "Сообщения", "бот помощь": "Помощь", "бот варпы": "Варп-команды",
    "бот игры": "Игры Предвестника", "бот вип": "VIP", "бот стрик": "Ваш стрик", "бот достижения": "Ваши достижения",
    "бот семья": "нет семьи", "бот настройка": "Предвестник", "бот мафия": "набор игроков",
}


@bot_scenario
async def dm_everyday_commands(h: Harness) -> None:
    (player,), _ = sim_friends(h, 1)
    for command, expected in DM_COMMANDS.items():
        sent = await say(h, player, player.id, command)
        ok(sent, f"{command!r} gets an answer in the DM")
        ok(expected in said(sent), f"{command!r} should answer with {expected!r}, got {said(sent)[:90]!r}")
        for _, params in sent:
            ok(int(params["chat_id"]) == player.id, f"{command!r} answers in the DM, not elsewhere")


@bot_scenario
async def group_everyday_commands(h: Harness) -> None:
    players, group = sim_friends(h, 3)
    for player in players:
        await say(h, player, group, "привет всем")
    for command, expected in GROUP_COMMANDS.items():
        sent = await say(h, players[0], group, command)
        ok(sent, f"{command!r} gets an answer in the group")
        ok(expected in said(sent), f"{command!r} should answer with {expected!r}, got {said(sent)[:90]!r}")
        for _, params in sent:
            ok(int(params["chat_id"]) == group, f"{command!r} answers in the group")
    top = await say(h, players[1], group, "бот топ")
    ok(f"sim{players[0].id}" in said(top), "the chat top lists the most active player")


@bot_scenario
async def group_word_without_bot_is_ignored(h: Harness) -> None:
    """Ordinary chatter in a group must not trigger commands: only «бот …» (and a few bare words) do."""
    (player,), group = sim_friends(h, 1)
    for text in ("баланс", "всем привет, как баланс", "топ 10 фильмов", "я устал", "помощь нужна"):
        ok(not await say(h, player, group, text), f"{text!r} is ordinary chat in a group, the bot stays silent")


@bot_scenario
async def warps_target_and_usage(h: Harness) -> None:
    actor, friend = h.user("Аня"), h.user("Борис")
    group = h.new_chat([actor, friend])
    for player in (actor, friend):
        await say(h, player, group, "привет")
    hug = await say(h, actor, group, f"бот обнять, @sim{friend.id}")
    ok(hug and "Аня" in said(hug) and f"sim{friend.id}" in said(hug), f"a warp names both players: {said(hug)!r}")
    ok("Формат команды" in said(await say(h, actor, group, "бот обнять")), "no target → the format hint")
    ok("Формат команды" in said(await say(h, actor, group, "бот перевод")), "a transfer without arguments → the format hint")
    dm = await say(h, actor, actor.id, "обнять")
    ok("Привет! Я бот" in said(dm), f"group-only commands in a DM fall back to the DM hint: {said(dm)[:70]!r}")


@bot_scenario
async def ship_and_article_commands(h: Harness) -> None:
    players, group = sim_friends(h, 4)
    for player in players:
        await say(h, player, group, "привет всем")
    ship = await say(h, players[0], group, "шипирить")
    ok(ship and said(ship).count("@sim") >= 2, f"the ship names a pair: {said(ship)!r}")
    article = await say(h, players[1], group, "моя статья")
    ok("Обвиняемый" in said(article) and f"sim{players[1].id}" in said(article), f"the article is about the asker: {said(article)[:100]!r}")
    again = await say(h, players[1], group, "моя статья")
    ok("Обвиняемый" not in said(again) and re.search(r"\d+ с", said(again)),
       f"asking again at once gets a cooldown notice with the seconds left, not a new case: {said(again)!r}")


@bot_scenario
async def transfer_money_with_double_tap(h: Harness) -> None:
    """Pay a friend through the buttons; pressing the same button twice moves the money once."""
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    from infrastructure.repositories import economy as eco

    sender, friend = h.user("Аня"), h.user("Борис")
    group = h.new_chat([sender, friend])
    for player in (sender, friend):
        await say(h, player, group, "привет")
    async with get_pool().acquire() as conn:
        await eco.add_balance(PGAdapter(conn), sender.id, mora=100, source="sim", note="scenario funds",
                              idempotency_key=f"sim-funds-{h.run_tag}-{sender.id}")
    ask = await say(h, sender, group, f"бот перевод, @sim{friend.id} 30")
    ok("Какую валюту отправить" in said(ask), said(ask))
    prompt = last_message(h, group, "Какую валюту")
    stale = dataclasses.replace(prompt, markup={"inline_keyboard": [list(r) for r in prompt.markup["inline_keyboard"]]})
    stranger = await h.click(friend, group, prompt, "Мора")
    ok(stranger.alert and "не ваш" in stranger.text, f"someone else's transfer cannot be confirmed: {stranger}")
    first = await h.click(sender, group, prompt, "Мора")
    ok(first.text == "Готово", f"the transfer goes through: {first}")
    second = await h.click(sender, group, stale, "Мора")          # a second tap on the already-answered message
    ok(second.text == "Готово", f"the repeat is acknowledged, not an error: {second}")

    async def wallet(user) -> str:
        return said(await say(h, user, user.id, "баланс"))

    ok("Мора: 70" in await wallet(sender), "the sender paid 30 once")
    ok("Мора: 30" in await wallet(friend), "the friend received 30 once")


@bot_scenario(volatile=True)
async def quests_command(h: Harness) -> None:
    """The daily quests are drawn at random: always answered and well-formed, never compared word for word."""
    players, group = sim_friends(h, 1)
    for chat, command in ((players[0].id, "квесты"), (group, "бот квесты")):
        sent = await say(h, players[0], chat, command)
        ok("КВЕСТЫ" in said(sent) and "Сегодня" in said(sent) and "0/" in said(sent), f"{command!r}: {said(sent)[:100]!r}")
