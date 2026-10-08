"""Scenarios: who may stop/resume a game, the quiet rules around commands, bystanders, topics."""
from __future__ import annotations

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import ok, scenario
from tools.mafia_sim.table import Table
from tools.mafia_sim.world import TgError

FIVE = ["citizen", "mafia", "citizen", "citizen", "citizen"]


async def _night_table(h: Harness, **kwargs) -> Table:
    t = await Table.create(h, 5, **kwargs)
    await t.start_with_roles(FIVE)
    return t


@scenario
async def host_can_stop_at_night(h: Harness) -> None:
    """The old gate ate the host's «стоп» in a quiet phase, so a stuck game could not be stopped."""
    t = await _night_table(h)
    ok(await t.phase() == "night", "game must be at night")
    mid = await h.say(t.host, t.chat, "бот мафия стоп")
    ok(not h.is_deleted(t.chat, mid), "a control command must pass the quiet-phase gate")
    ok(await t.phase() == "cancelled", f"the host's «стоп» must stop the game, phase={await t.phase()}")
    ok(h.world.last(t.chat, "Игра остановлена"), "the chat is told the game stopped")
    ok(t.action_message(t.users[1]) is None, "night buttons disappear after a stop")
    await h.say(t.host, t.chat, "бот мафия")
    ok(h.world.last(t.chat, "набор игроков"), "a new lobby can be created in the same chat right after a stop")


@scenario
async def stop_permissions(h: Harness) -> None:
    t = await _night_table(h)
    admin = t.add_bystander("Админ")
    h.world.set_member(t.chat, admin.id, "administrator", can_delete_messages=True, can_manage_chat=True)
    await h.say(t.users[2], t.chat, "бот мафия стоп")
    ok(await t.phase() == "night", "an ordinary player cannot stop the game")
    ok(h.world.last(t.chat, "хозяин игры или админ"), "and is told who can")
    chatter = await h.say(t.users[2], t.chat, "бот мафия квантовая")
    ok(h.is_deleted(t.chat, chatter), "only control commands bypass the quiet rule, not any text starting with «бот мафия»")
    rules = await h.say(t.users[3], t.chat, "бот мафия правила")
    ok(not h.is_deleted(t.chat, rules), "rules may be requested at night")
    await h.say(admin, t.chat, "бот мафия стоп")
    ok(await t.phase() == "cancelled", "a chat admin can stop a stuck game")


@scenario
async def stop_button_asks_first(h: Harness) -> None:
    t = await _night_table(h)
    refused = await t.press(t.users[3], "Остановить игру", "НОЧЬ")
    ok(refused.alert and "хозяин" in refused.text, f"strangers cannot stop: {refused.text}")
    await t.press(t.host, "Остановить игру", "НОЧЬ")
    confirm = h.world.last(t.chat, "Остановить игру?")
    ok(confirm, "stopping needs a confirmation message")
    await h.click(t.host, t.chat, confirm, "Нет")
    ok(confirm.deleted and await t.phase() == "night", "«Нет» keeps playing")
    await t.press(t.host, "Остановить игру", "НОЧЬ")
    await h.click(t.host, t.chat, h.world.last(t.chat, "Остановить игру?"), "Да, остановить")
    ok(await t.phase() == "cancelled", "«Да» stops the game")


@scenario
async def my_role_popup(h: Harness) -> None:
    t = await Table.create(h, 8, command="бот мафия 8 дон доктор детектив")
    outsider = t.add_bystander("Зритель")
    await t.start_with_roles(["citizen", "mafia", "don", "doctor", "detective", "citizen", "citizen", "citizen"])
    expect = {1: "Мафия", 2: "Дон", 3: "Доктор", 4: "Детектив", 0: "Мирный житель"}
    for index, word in expect.items():
        popup = await t.press(t.users[index], "Моя роль", "НОЧЬ")
        ok(popup.alert and word in popup.text and len(popup.text) <= 200, f"role popup for {word}: {popup.text}")
    ok("Игрок3" in (await t.press(t.users[1], "Моя роль", "НОЧЬ")).text, "the mafia popup lists the team")
    ok("не участвуешь" in (await t.press(outsider, "Моя роль", "НОЧЬ")).text, "an onlooker is told they are not playing")
    await t.pick(t.users[1], t.users[5])
    await t.pick(t.users[2], t.users[5])
    await t.next_phase()
    ok("выбыл" in (await t.press(t.users[5], "Моя роль", "ОБСУЖДЕНИЕ")).text, "a dead player is told so")


@scenario
async def forum_topics_and_reply_threads(h: Harness) -> None:
    reply = await Table.create(h, 4, topic=555, forum=False)  # plain reply thread: not a forum topic
    reply_row = await reply.match()
    ok(reply.lobby() is not None, "a lobby opened by replying must work")
    forum = await _forum_table(h)
    ok((await forum.match())["topic_id"] == 77, "a forum topic is stored")
    ok(h.world.last(forum.chat, "НОЧЬ").topic_id == 77, "the game card goes to the game's topic")
    ok(reply_row["topic_id"] is None, f"a reply chain must not become a phantom topic: {reply_row['topic_id']}")
    inside = await h.say(forum.users[2], forum.chat, "тише", topic=77)
    elsewhere = await h.say(forum.users[2], forum.chat, "общий разговор")
    other_topic = await h.say(forum.users[2], forum.chat, "другая тема", topic=78)
    ok(h.is_deleted(forum.chat, inside) and not h.is_deleted(forum.chat, elsewhere) and not h.is_deleted(forum.chat, other_topic),
       "the quiet rule applies only inside the game's own topic")


async def _forum_table(h: Harness) -> Table:
    t = await Table.create(h, 5, topic=77, command="бот мафия 5")
    row = await t.match()
    if row["topic_id"] is None:  # the harness marks topic messages as plain replies unless forum=True
        raise AssertionError("forum topic was not stored")
    await t.start_with_roles(FIVE)
    return t


@scenario
async def lost_delete_rights_pause_and_resume(h: Harness) -> None:
    t = await _night_table(h)
    h.world.fail(lambda name, params: name == "DeleteMessage", TgError(400, "Bad Request: message can't be deleted"), times=1)
    await h.say(t.users[2], t.chat, "шёпотом")
    ok(await t.phase() == "paused", "if the bot cannot delete, the game pauses instead of pretending")
    ok("ИГРА НА ПАУЗЕ" in t.card_text() and "удалять" in t.card_text(), f"the pause explains why: {t.card_text()}")
    h.world.set_member(t.chat, 123456, "administrator", can_delete_messages=False)
    refused = await t.press(t.host, "Продолжить", "ПАУЗЕ")
    ok(refused.alert and "права" in refused.text, f"resume needs the rights back: {refused.text}")
    h.world.set_member(t.chat, 123456, "administrator", can_delete_messages=True)
    stranger = await t.press(t.users[3], "Продолжить", "ПАУЗЕ")
    ok(stranger.alert, "only the host or an admin resumes")
    await t.press(t.host, "Продолжить", "ПАУЗЕ")
    row = await t.match()
    ok(row["phase"] == "night" and row["phase_deadline"] is not None, "resume restores the night with its remaining time")


@scenario
async def busy_chat_card_bump(h: Harness) -> None:
    t = await Table.create(h, 6)
    crowd = [t.add_bystander(f"Болтун{i}") for i in range(5)]
    await t.join_all()
    first = t.lobby()
    for i in range(26):
        await h.say(crowd[i % 5], t.chat, f"флуд {i}")
    cards = [m for m in h.world.live(t.chat) if "набор игроков" in m.text]
    ok(len(cards) == 1 and cards[0].message_id != first.message_id and first.deleted, "a buried lobby returns once, the old copy is removed")
    for i in range(30):
        await h.say(crowd[i % 5], t.chat, f"ещё флуд {i}")
    ok(len([m for m in h.world.live(t.chat) if "набор игроков" in m.text]) == 1 and not h.world.last(t.chat, "набор игроков").deleted,
       "bumps are rate-limited: no second card within 90 seconds")
    await h.sql("UPDATE predvestnik.mafia_v1_matches SET last_bump_at=CLOCK_TIMESTAMP()-INTERVAL '5 minutes' WHERE chat_id=$1", t.chat)
    await t.start()
    await h.sql("UPDATE predvestnik.mafia_v1_matches SET last_bump_at=NULL WHERE chat_id=$1", t.chat)
    await t.next_phase()
    old = h.world.last(t.chat, "ОБСУЖДЕНИЕ")
    for i in range(31):
        await h.say(crowd[i % 5], t.chat, f"обсуждаем {i}")
    new = h.world.last(t.chat, "ОБСУЖДЕНИЕ")
    ok(new.message_id != old.message_id and old.deleted, "the game card follows a busy chat down")
    ok(len([m for m in h.world.live(t.chat) if "ОБСУЖДЕНИЕ" in m.text]) == 1, "never two game cards")
