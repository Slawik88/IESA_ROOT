"""Scenarios: Telegram failures, races, abandoned games — the things that break in a real chat."""
from __future__ import annotations

import asyncio
import copy
import random
import re
from unittest import mock

from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter
from services import mafia_v1 as mafia
from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import ok, scenario
from tools.mafia_sim.table import Table
from tools.mafia_sim.world import NETWORK_FAULT, TgError

FIVE = ["citizen", "mafia", "citizen", "citizen", "citizen"]
SIX = ["citizen", "mafia", "doctor", "detective", "citizen", "citizen"]
CARD = re.compile(r"НОЧЬ|ОБСУЖДЕНИЕ|ГОЛОСОВАНИЕ")
FLOOD = TgError(429, "Too Many Requests: retry after 2", 2)


def _cards(h: Harness, t: Table) -> list:
    return [m for m in h.world.live(t.chat) if CARD.search(m.text) and m.buttons()]


async def _table(h: Harness, deck: list[str] = FIVE) -> Table:
    t = await Table.create(h, len(deck))
    await t.start_with_roles(deck)
    return t


@scenario
async def flood_on_edit_keeps_one_card(h: Harness) -> None:
    t = await _table(h)
    h.world.fail(lambda name, params: name == "EditMessageText", FLOOD, times=1)
    await t.next_phase()  # the card edit hits Telegram's flood limit
    ok(len(_cards(h, t)) == 1, f"a flood error must not create a second card: {[m.text[:20] for m in _cards(h, t)]}")
    await h.tick()  # the stored event resumes where it stopped
    cards = _cards(h, t)
    ok(len(cards) == 1 and "ОБСУЖДЕНИЕ" in cards[0].text, f"the card catches up on the next pass: {[m.text[:25] for m in cards]}")
    ok(sum("Рассвет" in m.text for m in h.world.live(t.chat)) == 1, "the dawn message is sent exactly once")


@scenario
async def flood_on_announcement_sends_once(h: Harness) -> None:
    t = await _table(h)
    h.world.fail(lambda name, params: name == "SendMessage" and params["chat_id"] == t.chat, FLOOD, times=1)
    await t.next_phase()
    ok(not h.world.last(t.chat, "Рассвет"), "the announcement waits while Telegram is flooded")
    await h.tick()
    await h.tick()
    ok(sum("Рассвет" in m.text for m in h.world.live(t.chat)) == 1, "retries must not duplicate the dawn message")
    ok((await t.match())["pending_event_json"] is None, "the finished event is cleared")


@scenario
async def deleted_card_is_recreated(h: Harness) -> None:
    t = await _table(h)
    old = _cards(h, t)[0]
    old.deleted = True  # an admin deleted the game card
    await h.sql("UPDATE predvestnik.mafia_v1_matches SET card_updated_at=NULL WHERE chat_id=$1", t.chat)
    await h.tick()
    cards = _cards(h, t)
    ok(len(cards) == 1 and cards[0].message_id != old.message_id, "a deleted card is replaced by exactly one new card")
    ok((await t.match())["phase_message_id"] == cards[0].message_id, "the new card is the bound one")


@scenario
async def one_broken_match_does_not_stall_the_rest(h: Harness) -> None:
    a, b = await _table(h), await _table(h)
    real = mafia.advance_due_match

    async def flaky(db, *, match_id):
        if match_id == (await a.match())["id"]:
            raise RuntimeError("boom")
        return await real(db, match_id=match_id)

    await a.h.expire(a.chat)
    await b.h.expire(b.chat)
    with mock.patch("services.mafia_v1.advance_due_match", flaky):
        await h.tick()
    ok(await b.phase() == "discussion", "the healthy match advanced although another one failed")
    ok(await a.phase() == "night", "the failing match is left untouched")
    await h.tick()
    ok(await a.phase() == "discussion", "and recovers on the next pass")


@scenario
async def closed_dm_pauses_then_resume_resends_only_missing(h: Harness) -> None:
    t = await _table(h, SIX)
    u = t.users
    await t.pick(u[1], u[4])
    await t.next_phase()
    await t.next_phase()
    h.world.dm_open.discard(u[1].id)  # the mafioso blocks the bot between the phases
    await t.next_phase()
    ok(await t.phase() == "paused", f"unreachable players pause the game, not freeze it: {await t.phase()}")
    ok("Игрок2" in t.card_text() and "Start" in t.card_text(), f"the pause card names who must open the bot: {t.card_text()}")
    row = await t.match()
    ok(row["pause_detail"] == "Игрок2", f"{row['pause_detail']}")
    h.world.dm_open.add(u[1].id)
    blocked_again = (await _count_prompts(h, t, u[2]), await _count_prompts(h, t, u[3]))
    ok(blocked_again == (1, 1), f"healthy night roles got their buttons once: {blocked_again}")
    await t.press(t.host, "Продолжить", "ПАУЗЕ")
    ok(await t.phase() == "night", "resume continues the night")
    counts = [await _count_prompts(h, t, user) for user in (u[1], u[2], u[3])]
    ok(counts == [1, 1, 1], f"resume sends buttons only to those who missed them, no duplicates: {counts}")


async def _count_prompts(h: Harness, t: Table, user) -> int:
    return sum(1 for m in h.dm(user) if any(b.get("callback_data", "").startswith("mfa:") for b in m.buttons()))


@scenario
async def abandoned_game_closes_itself(h: Harness) -> None:
    t = await Table.create(h, 4)
    await t.ready()
    for _ in range(8):
        if await t.phase() in ("cancelled", "finished"):
            break
        await t.next_phase()
    row = await t.match()
    ok(row["phase"] == "cancelled" and row["finished_reason"] == "abandoned", f"idle game must close: {row['phase']}/{row['finished_reason']}")
    ok(h.world.last(t.chat, "никто не нажимал"), "the chat is told why")
    receipts = await h.sql("SELECT COUNT(*) AS n FROM predvestnik.quest_v1_metric_receipts WHERE event_id=$1", f"mafia:{row['id']}")
    ok(receipts[0]["n"] == 0, "an abandoned game earns no quest progress")
    await h.say(t.host, t.chat, "бот мафия")
    ok(h.world.last(t.chat, "набор игроков"), "the chat is free for a new game")


@scenario
async def idle_lobby_expires(h: Harness) -> None:
    t = await Table.create(h, 5)
    await h.sql("UPDATE predvestnik.mafia_v1_matches SET last_activity_at=CLOCK_TIMESTAMP()-INTERVAL '31 minutes' WHERE chat_id=$1", t.chat)
    await h.tick()
    row = await t.match()
    ok(row["phase"] == "cancelled" and row["finished_reason"] == "lobby_expired", f"stale lobby must close: {row['phase']}")
    ok(h.world.last(t.chat, "Лобби закрыто"), "the old lobby card says it is closed")
    await h.say(t.host, t.chat, "бот мафия")
    ok(h.world.last(t.chat, "набор игроков"), "a new lobby can be opened")


@scenario
async def races_do_not_break_the_game(h: Harness) -> None:
    t = await Table.create(h, 5)
    await t.join_all()
    clicks = await asyncio.gather(*[t.start() for _ in range(5)])
    ok(sum("Роли отправлены" in c.text for c in clicks) == 1, f"exactly one start wins: {[c.text for c in clicks]}")
    ok(all(c.answered for c in clicks), "every tap is answered")
    ok([sum("Партия Мафии" in m.text for m in h.dm(u)) for u in t.users] == [1] * 5, "one role card per player")
    row = await t.match()
    await h.expire(t.chat)
    results = await asyncio.gather(*[_advance(row["id"]) for _ in range(3)])
    ok(sum(r is not None for r in results) == 1, "a phase closes exactly once under concurrent checks")
    ok(await t.phase() == "discussion", "and moves only one step")
    small = await Table.create(h, 6, command="бот мафия 4")
    joins = await asyncio.gather(*[h.click(u, small.chat, small.lobby(), "Войти") for u in small.users[1:]])
    seated = await h.sql("SELECT COUNT(*) AS n FROM predvestnik.mafia_v1_players WHERE match_id=$1", (await small.match())["id"])
    ok(seated[0]["n"] == 4 and sum(c.alert for c in joins) == 2, f"a full lobby seats exactly its capacity: {seated[0]['n']}")


async def _advance(match_id: int):
    async with get_pool().acquire() as conn:
        return await mafia.advance_due_match(PGAdapter(conn), match_id=match_id)


@scenario
async def stale_buttons_are_harmless(h: Harness) -> None:
    t = await _table(h)
    night_prompt = copy.deepcopy(t.action_message(t.users[1]))
    await t.pick(t.users[1], t.users[2])
    await t.next_phase()
    stale = await h.click(t.users[1], t.users[1].id, night_prompt, "#3 Игрок3")
    ok(stale.alert and "закончился" in stale.text, f"yesterday's night button explains itself: {stale.text}")
    await t.next_phase()
    voting = copy.deepcopy(h.world.last(t.chat, "ГОЛОСОВАНИЕ"))
    await t.next_phase()
    late = await h.click(t.users[0], t.chat, voting, "Никого")
    ok(late.alert and ("закончился" in late.text or "устарела" in late.text), f"a vote after the deadline is refused kindly: {late.text}")
    dead_vote = await h.click(t.users[2], t.users[2].id, night_prompt, "#3 Игрок3")
    ok(dead_vote.alert, "a dead or stale actor can never act")


@scenario
async def broken_quests_never_block_the_end(h: Harness) -> None:
    """Quest assignment failed in the first PG run: the game must still end and be announced."""
    flags = "('game_rhythm_v2','game_minesweeper_v2')"
    await h.sql(f"UPDATE predvestnik.system_flags SET enabled=0 WHERE key IN {flags}")
    try:
        t = await _table(h)
        await t.pick(t.users[1], t.users[2])
        await t.next_phase()
        await t.press(t.host, "К голосованию", "ОБСУЖДЕНИЕ")
        for voter in await t.alive():
            await t.vote(t.user(voter), t.users[1])
        await t.next_phase()
        ok(await t.phase() == "finished", f"quest trouble must not roll back the end of the game: {await t.phase()}")
        ok(h.world.last(t.chat, "Кто кем был"), "the players still get the result")
        row = await t.match()
        ok(row["pending_event_json"] is not None, "the failed receipts stay queued")
    finally:
        await h.sql(f"UPDATE predvestnik.system_flags SET enabled=1 WHERE key IN {flags}")
    await h.tick()
    row = await t.match()
    receipts = await h.sql("SELECT COUNT(*) AS n FROM predvestnik.quest_v1_metric_receipts WHERE metric='mafia_completed' AND event_id=$1", f"mafia:{row['id']}")
    ok(row["pending_event_json"] is None and receipts[0]["n"] == 5, f"receipts are issued once quests recover: {receipts[0]['n']}")


@scenario
async def flood_in_the_middle_of_role_delivery(h: Harness) -> None:
    t = await Table.create(h, 6)
    await t.join_all()
    h.world.fail(lambda name, params: name == "SendMessage" and params["chat_id"] == t.users[3].id, FLOOD, times=1)
    click = await t.start()
    ok(click.answered and not click.alert, f"the host gets a calm answer, not a crash: {click.text}")
    await h.tick()
    await h.tick()
    cards = [sum("Партия Мафии" in m.text for m in h.dm(u)) for u in t.users]
    ok(cards == [1] * 6, f"after the flood everybody has exactly one role card: {cards}")
    ok(await t.phase() == "night" and h.world.last(t.chat, "НОЧЬ 1"), "the first night card is posted")
    ok(h.world.last(t.chat, "МАФИЯ НАЧАЛАСЬ"), "the lobby card is retired")
    ok((await t.match())["pending_event_json"] is None, "nothing is left queued")


@scenario
async def undeliverable_role_cancels_cleanly(h: Harness) -> None:
    t = await Table.create(h, 5)
    await t.join_all()
    h.world.fail(lambda name, params: name == "SendMessage" and params["chat_id"] == t.users[2].id
                 and "Партия Мафии" in (params.get("text") or ""), TgError(403, "Forbidden: bot was blocked by the user"), times=1)
    click = await t.start()
    ok(click.alert and "отменена" in click.text, f"the host is told the game was cancelled: {click.text}")
    ok(await t.phase() == "cancelled" and (await t.match())["finished_reason"] == "private_role_delivery_failed", "match cancelled")
    note = h.world.last(t.chat, "Партия отменена")
    ok(note and t.users[2].name in note.text and "Старт" in note.text, f"the chat learns who must open the bot: {note and note.text}")
    ok(all(t.action_message(u) is None for u in t.users), "no live night buttons remain")
    await h.say(t.host, t.chat, "бот мафия")
    ok(h.world.last(t.chat, "набор игроков"), "a new lobby can be opened right away")


@scenario
async def chaos_during_delivery(h: Harness) -> None:
    """Telegram randomly floods / drops the connection while the scheduler delivers; games still end cleanly."""
    rng = random.Random(7)
    faults = (FLOOD, TgError(NETWORK_FAULT, "network"))

    def chaos(name: str, params: dict):
        return rng.choice(faults) if name in ("SendMessage", "EditMessageText", "EditMessageReplyMarkup", "DeleteMessage") and rng.random() < 0.15 else None

    for size in (5, 6, 8):
        t = await Table.create(h, size, command=f"бот мафия {size}")
        await t.ready()
        for _ in range(60):
            if await t.phase() in ("finished", "cancelled"):
                break
            phase = await t.phase()
            if phase in ("night", "voting"):
                for user in t.users:
                    msg = t.action_message(user)
                    if msg and rng.random() < 0.9:
                        buttons = [b for b in msg.buttons() if b.get("callback_data", "").startswith("mfa:")]
                        await h.click(user, user.id, msg, data_prefix="mfa:", index=rng.randrange(len(buttons)))
            await h.expire(t.chat)
            h.world.chaos = chaos
            for _ in range(3):
                await h.tick()
            h.world.chaos = None
            await h.tick()
        h.world.chaos = None
        for _ in range(4):  # let the retries settle
            await h.tick()
        row = await t.match()
        ok(row["phase"] in ("finished", "cancelled"), f"size {size}: the game must end despite faults, phase={row['phase']}")
        ok(row["pending_event_json"] is None, f"size {size}: queued events must drain: {row['pending_event_json']}")
        await _no_duplicates(h, t, size)


async def _no_duplicates(h: Harness, t: Table, size: int) -> None:
    row = await t.match()
    resolved = await h.sql("SELECT payload_json->>'previous_phase' AS p FROM predvestnik.mafia_v1_audit_events WHERE match_id=$1 AND event_type='phase_advanced'", row["id"])
    nights = sum(r["p"] == "night" for r in resolved)
    votes = sum(r["p"] == "voting" for r in resolved)
    texts = [m.text for m in h.world.live(t.chat)]
    ok(sum("Рассвет" in x for x in texts) == nights, f"size {size}: one dawn message per night ({nights}), got {sum('Рассвет' in x for x in texts)}")
    ok(sum("Итог голосования" in x for x in texts) == votes, f"size {size}: one result per vote ({votes})")
    for user in t.users:
        own = [m.text for m in h.dm(user)]
        ok(sum("Партия Мафии" in x for x in own) == 1, f"size {size}: {user.name} must have exactly one role card")
        prompts = [m.group(1) for x in own for m in [re.search(r"🌙 Ночь (\d+)\.", x)] if m and "Партия Мафии" not in x]
        ok(len(prompts) == len(set(prompts)), f"size {size}: {user.name} got a night prompt twice: {prompts}")
        ok(sum("Ты выбыл" in x for x in own) <= 1, f"size {size}: {user.name} told twice that they are out")
