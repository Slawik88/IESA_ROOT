"""Whole-bot scenarios: /start, deep links and the first minutes of a new player."""
from __future__ import annotations

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_util import button, said, say, sim_friends

MINIAPP = "https://miniapp.example/predvestnik/"


@bot_scenario
async def start_dm_first_screen(h: Harness) -> None:
    (player,), _ = sim_friends(h, 1)
    sent = await say(h, player, player.id, "/start")
    text = said(sent)
    ok("Предвестник" in text and "Добавьте меня в свой чат" in text, f"the first screen introduces the bot: {text[:120]!r}")
    markups = [p.get("reply_markup") for _, p in sent if p.get("reply_markup") is not None]
    ok(markups, "the first screen has buttons")
    labels = [b.text for m in markups for row in m.inline_keyboard for b in row]
    ok(any("чат" in label.lower() for label in labels), f"a button leads to adding the bot to a chat: {labels}")
    ok(any(name == "SendPhoto" for name, _ in sent), "the welcome picture is sent first")


@bot_scenario
async def start_deeplinks(h: Harness) -> None:
    (player,), group = sim_friends(h, 1)
    shop = await say(h, player, player.id, "/start buyzarniki")
    ok("ЗАРНИКИ" in said(shop) and "258" in said(shop), f"/start buyzarniki opens the Stars shop: {said(shop)[:100]!r}")
    labels = [b.text for _, p in shop for row in (p.get("reply_markup").inline_keyboard if p.get("reply_markup") else []) for b in row]
    ok(any("Своя сумма" in label for label in labels) and len(labels) >= 5, f"package buttons incl. a custom amount: {labels}")

    app = await say(h, player, player.id, "/start miniapp_profile")
    ok("Предвестник готов" in said(app), said(app)[:100])
    web = [b for _, p in app for row in p["reply_markup"].inline_keyboard for b in row]
    ok(web and web[0].web_app and web[0].web_app.url.startswith(MINIAPP), f"the Mini App button opens the app: {web}")

    rules = await say(h, player, player.id, "/start mrules")
    ok("Мафия" in said(rules), f"the Mafia lobby link explains the game: {said(rules)[:80]!r}")

    other = await say(h, player, player.id, f"/start setup_{group}")
    ok("Настраивать чат могут владелец и администраторы" in said(other), "a non-admin cannot open a chat's setup")

    bad = await say(h, player, player.id, "/start no_such_link")
    ok("Предвестник" in said(bad), "an unknown start parameter falls back to the first screen")


@bot_scenario
async def start_in_group(h: Harness) -> None:
    (player,), group = sim_friends(h, 1)
    sent = await say(h, player, group, "/start")
    ok(sent and "Я Предвестник" in said(sent), f"/start in a group leads to the chat setup text: {said(sent)[:100]!r}")
    for _, params in sent:
        ok(int(params["chat_id"]) == group, "the reply stays in the group")


@bot_scenario
async def dm_help_and_site(h: Harness) -> None:
    (player,), _ = sim_friends(h, 1)
    for command, expect in (("/help", "Помощь"), ("помощь", "Помощь"), ("/site", "Предвестник"), ("сайт", "Предвестник"),
                            ("/paysupport", "ПОДДЕРЖКА ПЛАТЕЖЕЙ"), ("/setup", "Мои чаты")):
        sent = await say(h, player, player.id, command)
        ok(expect in said(sent), f"{command!r} -> {expect!r}, got {said(sent)[:80]!r}")
