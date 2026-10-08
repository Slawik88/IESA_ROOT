"""Scenarios: creating a lobby, joining, settings, deep links and the start check."""
from __future__ import annotations

import json

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import ok, scenario
from tools.mafia_sim.table import Table


@scenario
async def lobby_basics(h: Harness) -> None:
    t = await Table.create(h, 5)
    card = t.lobby()
    ok(card and "Что делать" in card.text and "Нужно ещё 3" in card.text, f"lobby must explain the next step: {card and card.text}")
    ok(any("Как играть" in b["text"] for b in card.buttons()), "a newcomer needs a «Как играть» button")
    joined = await h.click(t.users[1], t.chat, card, "Войти")
    ok("Ты в лобби" in joined.text and joined.answered, f"join feedback missing: {joined}")
    await h.click(t.users[1], t.chat, t.lobby(), "Войти")  # double tap must not take two seats
    rows = await h.sql("SELECT COUNT(*) AS n FROM predvestnik.mafia_v1_players WHERE match_id=$1", (await t.match())["id"])
    ok(rows[0]["n"] == 2, f"double join must keep one seat per person, got {rows[0]['n']}")
    leave_host = await h.click(t.host, t.chat, t.lobby(), "Выйти")
    ok(leave_host.alert and "Хозяин" in leave_host.text, f"host leaving must be explained: {leave_host.text}")
    left = await h.click(t.users[1], t.chat, t.lobby(), "Выйти")
    ok("вышел" in left.text, f"leave feedback: {left.text}")
    stranger = await h.click(t.users[2], t.chat, t.lobby(), "Начать")
    ok(stranger.alert and "только хозяин" in stranger.text, f"only the host starts: {stranger.text}")
    foreign = await h.click(t.users[2], t.chat, t.lobby(), "Настройки")
    ok(foreign.alert and "только хозяин" in foreign.text, f"only the host configures: {foreign.text}")


@scenario
async def command_variants(h: Harness) -> None:
    for command in ("бот мафия", "Бот, мафия!", "бот,мафия", "/mafia", "/mafia@predvestnik_test_bot"):
        t = await Table.create(h, 4, command=command)
        ok(t.lobby(), f"«{command}» must open a lobby")
    t = await Table.create(h, 4, command="бот мафия 6 доктор открытое быстро")
    row = await t.match()
    ok(row["max_players"] == 6 and row["vote_mode"] == "open" and row["tempo"] == "fast", f"inline settings ignored: {row}")
    roles = row["enabled_roles_json"]
    ok(json.loads(roles) == ["doctor"] and not row["roles_auto"], "an explicit role must switch off the «авто» roles")
    t = await Table.create(h, 4, command="бот мафия квантовая")
    ok(not t.lobby(), "unknown settings must not open a lobby")
    hint = h.world.last(t.chat, "Не понял")
    ok(hint and "бот мафия" in hint.text, f"a typo must produce a helpful hint: {[m.text for m in h.world.live(t.chat)]}")


@scenario
async def bot_without_rights(h: Harness) -> None:
    users = [h.user("Хозяин")]
    chat = h.new_chat(users, bot_can_delete=False)
    await h.say(users[0], chat, "бот мафия")
    reply = h.world.last(chat, "Удалять сообщения")
    ok(reply and "Администраторы" in reply.text, f"the owner must be told how to give rights: {[m.text for m in h.world.live(chat)]}")
    ok(not h.world.last(chat, "набор игроков"), "no lobby without delete rights")


@scenario
async def settings_flow(h: Harness) -> None:
    t = await Table.create(h, 5)
    await h.click(t.host, t.chat, t.lobby(), "Настройки")
    ok("Настройка партии" in t.lobby().text, "settings screen must open on the lobby card")
    await h.click(t.host, t.chat, t.lobby(), "Классика")
    row = await t.match()
    ok(not row["roles_auto"], "choosing a preset leaves «авто»")
    await h.click(t.host, t.chat, t.lobby(), "Авто")
    ok((await t.match())["roles_auto"], "«Авто» preset must switch auto roles back on")
    await h.click(t.host, t.chat, t.lobby(), "Роли")
    await h.click(t.host, t.chat, t.lobby(), "Дон")
    ok(not (await t.match())["roles_auto"], "toggling a role leaves auto mode")
    await h.click(t.host, t.chat, t.lobby(), "← Назад")
    await h.click(t.host, t.chat, t.lobby(), "Игроки")
    refused = await h.click(t.host, t.chat, t.lobby(), "6")
    ok(refused.alert and "от 8" in refused.text, f"Don with 6 seats must be refused plainly: {refused.text}")
    ok((await t.match())["max_players"] == 12, "a refused setting must not be saved")
    await h.click(t.host, t.chat, t.lobby(), "← Назад")
    await h.click(t.host, t.chat, t.lobby(), "Темп")
    await h.click(t.host, t.chat, t.lobby(), "Быстрый")
    ok((await t.match())["tempo"] == "fast", "tempo must be saved")
    await h.click(t.host, t.chat, t.lobby(), "← Назад")
    await h.click(t.host, t.chat, t.lobby(), "Готово")
    ok("набор игроков" in t.lobby().text and "ночь 40 с" in t.lobby().text, "back to the lobby, showing the fast tempo")


@scenario
async def deep_link_join(h: Harness) -> None:
    host, guest = h.user("Хозяин"), h.user("Гость", dm=False)
    chat = h.new_chat([host, guest])
    await h.say(host, chat, "бот мафия")
    lobby = h.world.last(chat, "набор игроков")
    match_id = (await h.match_row(chat))["id"]
    click = await h.click(guest, chat, lobby, "Войти")
    ok(click.url and f"start=mj{match_id}" in click.url, f"a closed DM must open the bot with a join link: {click}")
    ok("Гость" not in h.world.last(chat, "набор игроков").text, "the guest is not seated before pressing Start")
    h.world.dm_open.add(guest.id)  # the guest taps the link and presses Start
    await h.say(guest, guest.id, f"/start mj{match_id}")
    ok("Гость" in h.world.last(chat, "набор игроков").text, "the deep link must seat the guest and refresh the lobby card")
    ok(any("Ты в лобби" in m.text for m in h.dm(guest)), "the guest needs a confirmation in the private chat")
    outsider = h.user("Чужой")
    await h.say(outsider, outsider.id, f"/start mj{match_id}")
    ok(any("вступи в группу" in m.text for m in h.dm(outsider)), "someone outside the group must be told to join it first")
    await h.say(guest, guest.id, "/start mj999999999")
    ok(any("закрыто" in m.text for m in h.dm(guest)), "a dead link must say so")


@scenario
async def start_ignores_stored_ready_flag(h: Harness) -> None:
    """Regression: 'chat is not active with the bot' although everybody had an active chat."""
    t = await Table.create(h, 5)
    await t.join_all()
    await h.sql("DELETE FROM predvestnik.mafia_v1_dm_ready WHERE user_id = ANY($1::bigint[])", [u.id for u in t.users])
    click = await t.start()
    ok("Роли отправлены" in click.text, f"a missing «Я готов» record must never block the start: {click.text}")
    ok(await t.phase() == "night", "the game must be running")


@scenario
async def start_checks(h: Harness) -> None:
    t = await Table.create(h, 5)
    await h.click(t.users[1], t.chat, t.lobby(), "Войти")
    few = await t.start()
    ok(few.alert and "минимум 4" in few.text, f"too few players: {few.text}")
    await t.join_all()
    h.world.dm_open.discard(t.users[2].id)  # one player blocked the bot after joining
    blocked = await t.start()
    ok(blocked.alert and t.users[2].name in blocked.text and "Старт" in blocked.text, f"name the blocked player: {blocked.text}")
    ok(await t.phase() == "lobby", "a failed start must keep the lobby intact")
    h.world.dm_open.add(t.users[2].id)
    h.world.set_member(t.chat, t.users[3].id, "restricted", can_send_messages=False)
    muted = await t.start()
    ok(muted.alert and t.users[3].name in muted.text and "писать" in muted.text, f"muted player must be named: {muted.text}")
    h.world.set_member(t.chat, t.users[3].id, "member")
    h.world.set_member(t.chat, t.users[4].id, "left")
    gone = await t.start()
    ok(gone.alert and t.users[4].name in gone.text, f"a player who left the chat must be named: {gone.text}")
    h.world.set_member(t.chat, t.users[4].id, "member")
    ok("Роли отправлены" in (await t.start()).text, "everything fixed — the game starts")


@scenario
async def rules_and_private_entry(h: Harness) -> None:
    t = await Table.create(h, 4)
    await h.say(t.users[1], t.chat, "бот мафия правила")
    reply = h.world.last(t.chat, "Правила Мафии")
    ok(reply and any("start=mrules" in (b.get("url") or "") for b in reply.buttons()), "rules command must offer a deep link")
    user = t.users[1]
    await h.say(user, user.id, "/start mrules")
    page = h.world.last(user.id, "Мафия — что это")
    ok(page and "Нужно от 4 игроков" in page.text, "the deep link must open the first rules page in DM")
    await h.click(user, user.id, page, "Роли")
    ok("Роли" in h.world.last(user.id, "Мирный житель").text, "page buttons must switch pages")
    await h.say(user, user.id, "бот мафия")
    entry = h.world.last(user.id, "играется в групповом чате")
    ok(entry and any("Как играть" in b["text"] for b in entry.buttons()), "writing «бот мафия» in DM must explain, not fail")
    rules_button = next(b for b in t.lobby().buttons() if "Как играть" in b["text"])
    ok("start=mrules" in rules_button.get("url", ""), "the lobby «Как играть» is a link to the bot rules")


@scenario
async def start_rechecks_bot_rights(h: Harness) -> None:
    t = await Table.create(h, 5)
    await t.join_all()
    h.world.set_member(t.chat, 123456, "administrator", can_delete_messages=False)
    refused = await t.start()
    ok(refused.alert and "удалять" in refused.text and await t.phase() == "lobby", f"lost rights must stop the start, not the game later: {refused.text}")
    h.world.set_member(t.chat, 123456, "administrator", can_delete_messages=True)
    ok("Роли отправлены" in (await t.start()).text, "after the rights are back the game starts")
    for payload in ("mj" + "9" * 40, "mjabc", "mx1"):
        await h.say(t.users[1], t.users[1].id, f"/start {payload}")  # must never crash or stay silent
    ok(any("Предвестник" in m.text or "закрыто" in m.text for m in h.dm(t.users[1])), "garbage links fall back to the normal greeting")


@scenario
async def repeating_the_command_finds_the_game(h: Harness) -> None:
    t = await Table.create(h, 5)
    bystander = t.add_bystander("Любопытный")
    first = t.lobby()
    await h.say(bystander, t.chat, "бот мафия")
    ok(t.lobby().message_id == first.message_id and h.world.last(t.chat, "уже идёт"), "a second command right away points to the existing card instead of spamming")
    await h.sql("UPDATE predvestnik.mafia_v1_matches SET last_bump_at=CLOCK_TIMESTAMP()-INTERVAL '2 minutes' WHERE chat_id=$1", t.chat)
    await h.say(bystander, t.chat, "бот мафия")
    ok(first.deleted and len([m for m in h.world.live(t.chat) if "набор игроков" in m.text]) == 1, "later the lobby card is brought back, once")
    await t.join_all()
    await t.start()
    await h.sql("UPDATE predvestnik.mafia_v1_matches SET last_bump_at=NULL WHERE chat_id=$1", t.chat)
    await h.say(bystander, t.chat, "бот мафия статус")
    ok(len([m for m in h.world.live(t.chat) if "НОЧЬ" in m.text and m.buttons()]) == 1, "the running game's card is shown again, never duplicated")
    await h.say(bystander, t.chat, "бот мафия &<x>")
    ok(not [m for m in h.world.live(t.chat) if "Не понял" in m.text], "while a game runs, odd words after the command only show the game")
    t2 = await Table.create(h, 4, command="бот мафия a&b<c>d" + "x" * 40)
    ok(h.world.last(t2.chat, "Не понял") is not None, "odd settings words are escaped and answered, never an HTML error")
