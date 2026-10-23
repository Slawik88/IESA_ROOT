"""Scenarios from the bug hunt: long Telegram floods, buttons of old games, a rematch with the module off, lobby cleanup."""
from __future__ import annotations

import copy
from unittest import mock

from bot.chat import mafia as chat_mafia
from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter
from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import ok, scenario
from tools.mafia_sim.table import Table
from tools.mafia_sim.world import TgError

FIVE = ["citizen", "mafia", "citizen", "citizen", "citizen"]
FLOOD = TgError(429, "Too Many Requests: retry after 2", 2)
FLOOD30 = TgError(429, "Too Many Requests: retry after 30", 30)


async def _night(h: Harness) -> Table:
    t = await Table.create(h, 5)
    await t.start_with_roles(FIVE)
    return t


async def _town_wins(t: Table) -> None:
    """Night → discussion → everybody votes the mafioso out; the vote closes and the game ends."""
    await t.pick(t.users[1], t.users[2])
    await t.next_phase()
    await t.press(t.host, "К голосованию", "ОБСУЖДЕНИЕ")
    for voter in await t.alive():
        await t.vote(t.user(voter), t.users[1])


async def _module(h: Harness, chat: int, on: bool) -> None:
    await h.sql("INSERT INTO predvestnik.chat_settings (chat_id, chat_title, module_mafia) VALUES ($1, 'Sim', $2) "
                "ON CONFLICT (chat_id) DO UPDATE SET module_mafia = $2", chat, 1 if on else 0)


@scenario
async def flood_wait_is_respected(h: Harness) -> None:
    """Telegram says «подождите 30 секунд»: the scheduler must not hammer it again every two seconds."""
    t = await _night(h)
    h.world.fail(lambda name, params: name == "SendMessage" and params["chat_id"] == t.chat, FLOOD30, times=1)
    await t.next_phase()
    ok(not h.world.last(t.chat, "Рассвет"), "the dawn message waits while Telegram is flooded")
    sent = len(h.world.api("SendMessage"))
    await h.tick(time_passes=False)
    ok(len(h.world.api("SendMessage")) == sent, "no retry before the pause Telegram asked for has passed")
    await h.tick()
    ok(h.world.last(t.chat, "Рассвет"), "and the message arrives once the pause is over")


@scenario
async def long_flood_does_not_lose_the_end(h: Harness) -> None:
    """Forty failed attempts used to drop the stored event: the final message and every reward were lost."""
    t = await _night(h)
    await _town_wins(t)
    h.world.fail(lambda name, params: name in ("SendMessage", "EditMessageText") and params["chat_id"] == t.chat, FLOOD, times=40)
    await t.next_phase()
    for _ in range(80):
        if (await t.match())["pending_event_json"] is None:
            break
        await h.tick()
    row = await t.match()
    ok(row["phase"] == "finished" and row["pending_event_json"] is None, f"the event is delivered in the end: {row['phase']}")
    ok(h.world.last(t.chat, "победили мирные"), "the result reaches the chat")
    receipts = await h.sql("SELECT COUNT(*) AS n FROM predvestnik.quest_v1_metric_receipts WHERE metric='mafia_completed' AND event_id=$1",
                           f"mafia:{row['id']}")
    ok(receipts[0]["n"] == 5, f"everybody gets the receipt: {receipts[0]['n']}")


@scenario
async def long_dm_flood_does_not_leave_players_without_roles(h: Harness) -> None:
    t = await Table.create(h, 6)
    await t.join_all()
    late = {u.id for u in t.users[3:]}
    h.world.fail(lambda name, params: name == "SendMessage" and params["chat_id"] in late, FLOOD, times=20)
    await t.start()
    for _ in range(60):
        if (await t.match())["pending_event_json"] is None:
            break
        await h.tick()
    cards = [sum("Партия Мафии" in m.text for m in h.dm(u)) for u in t.users]
    ok(cards == [1] * 6, f"everybody gets exactly one role: {cards}")
    ok(await t.phase() == "night" and h.world.last(t.chat, "МАФИЯ НАЧАЛАСЬ"), "the game starts and the lobby card is retired")


@scenario
async def hopeless_delivery_still_pays_out_and_cancels_roleless_games(h: Harness) -> None:
    with mock.patch("bot.chat.mafia_delivery.MAX_ATTEMPTS", 3):
        t = await _night(h)
        await _town_wins(t)
        h.world.fail(lambda name, params: params.get("chat_id") == t.chat and name in ("SendMessage", "EditMessageText"),
                     FLOOD, times=999)
        await t.next_phase()
        for _ in range(10):
            await h.tick()
        row = await t.match()
        ok(row["pending_event_json"] is None, "a lost event does not stay queued forever")
        receipts = await h.sql("SELECT COUNT(*) AS n FROM predvestnik.quest_v1_metric_receipts WHERE metric='mafia_completed' "
                               "AND event_id=$1", f"mafia:{row['id']}")
        ok(receipts[0]["n"] == 5, f"rewards do not depend on the chat message: {receipts[0]['n']}")
        h.world.failures.clear()
        # Роли не дошли за все попытки — партию отменяем, а не оставляем играть без ролей.
        u = Table(h, [h.user(f"Игрок{i}") for i in range(1, 6)], 0)
        u.chat = h.new_chat(u.users)
        await h.say(u.users[0], u.chat, "бот мафия")
        await u.join_all()
        late = {x.id for x in u.users[2:]}
        h.world.fail(lambda name, params: name in ("SendMessage", "SendPhoto") and params["chat_id"] in late, FLOOD, times=999)
        await u.start()
        for _ in range(10):
            await h.tick()
        row = await u.match()
        ok(row["phase"] == "cancelled" and row["finished_reason"] == "private_role_delivery_failed",
           f"{row['phase']}/{row['finished_reason']}")
        h.world.failures.clear()
        await h.tick()
        ok(h.world.last(u.chat, "Партия отменена"), "the chat learns the game was cancelled")


@scenario
async def old_buttons_cannot_stop_the_next_game(h: Harness) -> None:
    t = await _night(h)
    await t.press(t.host, "Остановить игру", "НОЧЬ")
    old_confirm = copy.deepcopy(h.world.last(t.chat, "Остановить игру?"))
    await h.say(t.host, t.chat, "бот мафия стоп")
    await h.say(t.host, t.chat, "бот мафия")
    await t.start_with_roles(FIVE)
    ok(await t.phase() == "night", "the second game is running")
    click = await h.click(t.host, t.chat, old_confirm, "Да, остановить")
    ok(click.alert and "прошлой партии" in click.text, f"the old confirmation explains itself: {click.text}")
    ok(await t.phase() == "night", "and does not stop the new game")


@scenario
async def old_lobby_card_cannot_cancel_the_new_lobby(h: Harness) -> None:
    t = await Table.create(h, 5)
    old = copy.deepcopy(t.lobby())
    await h.click(t.host, t.chat, t.lobby(), "Отменить лобби")
    ok(await t.phase() == "cancelled", "the first lobby is cancelled")
    await h.say(t.host, t.chat, "бот мафия")
    ok(await t.phase() == "lobby", "a new lobby is open")
    click = await h.click(t.host, t.chat, old, "Отменить лобби")
    ok(click.alert and "прошлого лобби" in click.text, f"the old lobby card explains itself: {click.text}")
    ok(await t.phase() == "lobby", "the new lobby survives")


@scenario
async def rematch_respects_the_module_switch(h: Harness) -> None:
    t = await _night(h)
    await _town_wins(t)
    await t.next_phase()
    ok(await t.phase() == "finished", "the game is over")
    final = h.world.last(t.chat, "победили мирные")
    lobby = await Table.create(h, 5)
    await _module(h, t.chat, False)
    await _module(h, lobby.chat, False)
    try:
        click = await h.click(t.host, t.chat, final, "ещё")
        ok(click.alert, f"«Сыграть ещё» is refused while the section is off: {click.text}")
        ok(await t.phase() == "finished", "no new lobby appeared")
        join = await h.click(lobby.users[1], lobby.chat, lobby.lobby(), "Войти")
        ok(join.alert, f"joining is refused while the section is off: {join.text}")
        start = await h.click(lobby.host, lobby.chat, lobby.lobby(), "Начать")
        ok(start.alert and "Роли отправлены" not in start.text, f"starting is refused: {start.text}")
    finally:   # номера чатов симулятора повторяются между запусками: выключенный раздел не должен остаться в базе
        await h.sql("DELETE FROM predvestnik.chat_settings WHERE chat_id = ANY($1::bigint[])", [t.chat, lobby.chat])


@scenario
async def non_host_start_costs_nothing(h: Harness) -> None:
    t = await Table.create(h, 8)
    await t.join_all()
    before = len(h.world.calls)
    click = await h.click(t.users[3], t.chat, t.lobby(), "Начать")
    ok(click.alert and "хозяин" in click.text, f"a stranger is told who can start: {click.text}")
    probes = [n for n, _ in h.world.calls[before:] if n in ("GetChatMember", "SendChatAction")]
    ok(not probes, f"a stranger's tap must not probe every player: {probes}")


@scenario
async def players_who_left_the_chat_are_dropped_at_start(h: Harness) -> None:
    t = await Table.create(h, 5)
    await t.join_all()
    h.world.set_member(t.chat, t.users[3].id, "left")
    click = await t.start()
    ok(click.alert and t.users[3].name in click.text and "убран" in click.text, f"the host is told who was removed: {click.text}")
    seated = await h.sql("SELECT COUNT(*) AS n FROM predvestnik.mafia_v1_players WHERE match_id=$1", (await t.match())["id"])
    ok(seated[0]["n"] == 4 and await t.phase() == "lobby", f"the lobby goes on without them: {seated[0]['n']}")
    again = await t.start()
    ok("Роли отправлены" in again.text, f"and the second try starts: {again.text}")


@scenario
async def purge_does_not_turn_a_lobby_into_a_vote(h: Harness) -> None:
    t = await Table.create(h, 5)
    await t.join_all()
    async with get_pool().acquire() as conn:
        await chat_mafia.pause_for_purge(PGAdapter(conn), h.bot, t.chat, None)
    ok(not h.world.last(t.chat, "ГОЛОСОВАНИЕ"), "a purge must not announce a vote in a lobby")
    ok(await t.phase() == "lobby", "the lobby stays a lobby")


@scenario
async def control_commands_pass_in_every_spelling(h: Harness) -> None:
    t = await _night(h)
    for text, passes in (("bot мафия правила", True), ("bot mafia правила", True), ("бот mafia статус", True),
                         ("/mafia стоп", False), ("бот мафия привет", False)):
        mid = await h.say(t.users[2], t.chat, text)
        ok(h.is_deleted(t.chat, mid) != passes, f"«{text}»: deleted={h.is_deleted(t.chat, mid)}")


@scenario
async def edits_do_not_bypass_the_quiet_night(h: Harness) -> None:
    t = await Table.create(h, 5)
    mid = await h.say(t.users[2], t.chat, "привет")     # лобби: писать можно
    await t.start_with_roles(FIVE)
    ok(not h.is_deleted(t.chat, mid), "the message was fine when it was written")
    await h.edit(t.users[2], t.chat, mid, "мафия — это Игрок2")
    ok(h.is_deleted(t.chat, mid), "an edit during the night is removed like any night message")
    other = await h.say(t.add_bystander("Зритель"), t.chat, "зритель")
    await h.edit(t.add_bystander("Зритель2"), t.chat, other, "правка зрителя")
    ok(not h.is_deleted(t.chat, other), "onlookers may edit")
