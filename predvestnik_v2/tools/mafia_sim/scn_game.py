"""Scenarios: whole games played through buttons and DMs."""
from __future__ import annotations

import random

from core import mafia_v1 as rules
from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import ok, scenario
from tools.mafia_sim.table import Table

FIVE = ["citizen", "mafia", "citizen", "citizen", "citizen"]
EIGHT = ["citizen", "mafia", "don", "doctor", "detective", "citizen", "citizen", "citizen"]


async def _remaining(h: Harness, t: Table) -> float:
    rows = await h.sql("SELECT EXTRACT(EPOCH FROM (phase_deadline - CLOCK_TIMESTAMP())) AS s "
                       "FROM predvestnik.mafia_v1_matches WHERE id=$1", (await t.match())["id"])
    return float(rows[0]["s"])


@scenario
async def town_wins(h: Harness) -> None:
    t = await Table.create(h, 5)
    bystander = t.add_bystander("Зритель")
    await t.start_with_roles(FIVE)
    u1, u2, u3, u4, u5 = t.users
    ok("Мафия" in h.dm(u2)[0].text and "Цель" in h.dm(u2)[0].text, "the mafia role card must state the goal")
    ok(not h.dm(u1)[0].buttons(), "a citizen has no night buttons")
    pick = await t.pick(u2, u3)
    ok("Выбор принят" in pick.text and "закончится через" in pick.text, f"the lone mafioso finishing the night closes it early: {pick.text}")
    ok("Выбрано: #3 Игрок3" in t.action_message(u2).text and "✅ #3 Игрок3" in [b["text"] for b in t.action_message(u2).buttons()],
       "the DM must confirm the choice and mark the button")
    ok(any("Игрок3" in m.text for m in h.dm(u2) if "Команда мафии" in m.text), "the mafia board must show the pick")
    ok(0 < await _remaining(h, t) <= rules.NIGHT_MIN_SECONDS, "the early close respects the floor")
    await t.pick(u2, u4)  # changed mind
    await t.next_phase()
    ok(await t.phase() == "discussion", "dawn starts the discussion")
    dawn = h.world.last(t.chat, "Рассвет")
    ok(dawn and "Игрок4" in dawn.text and "Игрок1" in dawn.text, f"dawn names the victim and pings the living: {dawn and dawn.text}")
    ok(any("выбыл" in m.text for m in h.dm(u4)), "the eliminated player gets a DM")
    ok(t.action_message(u2) is None, "night buttons are removed once the night is over")
    for who, deleted in ((u1, False), (u4, True), (bystander, False)):
        mid = await h.say(who, t.chat, "мысли вслух")
        ok(h.is_deleted(t.chat, mid) == deleted, f"discussion gate wrong for {who.name}: deleted={h.is_deleted(t.chat, mid)}")
    old = h.world.last(t.chat, "ОБСУЖДЕНИЕ")
    await t.press(u1, "К голосованию", "ОБСУЖДЕНИЕ")
    voting = h.world.last(t.chat, "ГОЛОСОВАНИЕ")
    ok(voting and voting.message_id != old.message_id and old.deleted, "voting starts on a fresh card at the bottom")
    ok(all(any("Голосование" in m.text for m in h.dm(u)) for u in (u1, u2, u3, u5)), "every living player gets a ballot in DM")
    await t.vote(u1, u2)
    await h.click(u3, u3.id, t.action_message(u3), "#2 Игрок2")  # vote from DM
    await t.vote(u5, u2)
    last = await t.vote(u2, u1)
    ok("закончится через" in last.text, "the last ballot closes the vote early")
    await t.next_phase()
    ok(await t.phase() == "finished", f"killing the only mafioso ends the game: {await t.phase()}")
    final = h.world.last(t.chat, "победили мирные")
    ok(final and "Игрок2 — 🔫 Мафия" in final.text, f"final message reveals roles: {final and final.text}")
    row = await t.match()
    receipts = await h.sql("SELECT COUNT(*) AS n FROM predvestnik.quest_v1_metric_receipts WHERE metric='mafia_completed' AND event_id=$1",
                           f"mafia:{row['id']}")
    ok(receipts[0]["n"] == 5 and row["pending_event_json"] is None, "5 receipts and nothing left to deliver")
    again = await h.click(u3, t.chat, final, "Сыграть ещё")
    ok("Новое лобби" in again.text and t.lobby() and "Игрок3" in t.lobby().text, "«Сыграть ещё» opens a new lobby for the presser")


@scenario
async def mafia_wins(h: Harness) -> None:
    t = await Table.create(h, 4)
    await t.start_with_roles(["citizen", "mafia", "citizen", "citizen"])
    u1, u2, u3, u4 = t.users
    await t.pick(u2, u3)
    await t.next_phase()
    await t.next_phase()  # discussion ends by itself
    ok(await t.phase() == "voting", "discussion timer ends in voting")
    await t.next_phase()  # nobody votes
    ok("никто не выбыл" in h.world.last(t.chat, "Итог голосования").text, "an empty vote eliminates nobody")
    ok(await t.phase() == "night", "night 2 follows")
    await t.pick(u2, u4)
    await t.next_phase()
    ok(await t.phase() == "finished" and (await t.match())["winner"] == "mafia", "mafia equals town → mafia wins")
    ok(h.world.last(t.chat, "победила мафия"), "the group is told who won")


@scenario
async def early_close(h: Harness) -> None:
    t = await Table.create(h, 6)
    await t.start_with_roles(["citizen", "mafia", "doctor", "detective", "citizen", "citizen"])
    u1, u2, u3, u4, u5, u6 = t.users
    first = await t.pick(u2, u5)
    second = await t.pick(u3, u5)
    ok("закончится через" not in first.text + second.text, "the night must wait for the detective")
    ok(await _remaining(h, t) > 40, "no early close yet")
    last = await t.pick(u4, u2)
    ok("закончится через" in last.text, "all three night roles acted")
    left = await _remaining(h, t)
    ok(4 <= left <= rules.NIGHT_MIN_SECONDS, f"close within the floor, not instantly: {left}")
    fix = await t.pick(u4, u6)  # misclick can still be fixed
    ok("Выбор принят" in fix.text, "the last player can still correct a misclick")
    await t.next_phase()
    ok("прошла спокойно" in h.world.last(t.chat, "Рассвет").text, "the doctor saved the victim → a quiet night")
    ok(any("не мафия" in m.text for m in h.dm(u4)), "the detective gets the check result")


@scenario
async def don_tie_break_and_board(h: Harness) -> None:
    t = await Table.create(h, 8, command="бот мафия 8 дон доктор детектив")
    await t.start_with_roles(EIGHT)
    u = t.users
    ok("Дон" in h.dm(u[1])[0].text and "Игрок3" in h.dm(u[1])[0].text, "the mafioso sees the Don among teammates")
    ok(not any("Команда мафии" in m.text for m in h.dm(u[0])), "citizens never see the mafia board")
    await t.pick(u[1], u[5])
    await t.pick(u[2], u[6])  # the Don disagrees
    board = next(m for m in h.dm(u[1]) if "Команда мафии" in m.text)
    ok("Игрок3 (Дон): #7 Игрок7" in board.text, f"the board shows teammates' picks live: {board.text}")
    await t.pick(u[3], u[0])
    await t.pick(u[4], u[1])
    await t.next_phase()
    ok("Игрок7" in h.world.last(t.chat, "Рассвет").text, "a tie goes to the Don's choice")
    ok(any("МАФИЯ" in m.text for m in h.dm(u[4])), "the detective found the mafioso")


@scenario
async def earlier_pick_wins_without_don(h: Harness) -> None:
    t = await Table.create(h, 8, command="бот мафия 8")
    await t.start_with_roles(["citizen", "mafia", "mafia", "citizen", "citizen", "citizen", "citizen", "citizen"])
    u = t.users
    await t.pick(u[1], u[5])
    await t.pick(u[2], u[6])
    await t.next_phase()
    ok("Игрок6" in h.world.last(t.chat, "Рассвет").text, "without a Don the earlier choice decides a tie")


@scenario
async def random_games(h: Harness) -> None:
    """Black box: random players, random sizes; every game must end sanely and respect the quiet rules."""
    rng = random.Random(20261008)
    for size in (4, 5, 6, 7, 8, 9, 12):
        t = await Table.create(h, size, command=f"бот мафия {size}")
        watcher = t.add_bystander("Зритель")
        await t.ready()
        roles = await t.roles()
        for step in range(150):
            phase = await t.phase()
            if phase in ("finished", "cancelled"):
                break
            alive = set(await t.alive())
            for user in t.users + [watcher]:
                kept = await _chatter_ok(h, t, user, phase, alive)
                ok(kept, f"size {size} {phase}: gate wrong for {user.name}")
            if phase in ("night", "voting"):
                for user in t.users:
                    msg = t.action_message(user)
                    if msg and rng.random() < 0.9:
                        buttons = [b for b in msg.buttons() if b.get("callback_data", "").startswith("mfa:")]
                        click = await h.click(user, user.id, msg, data_prefix="mfa:", index=rng.randrange(len(buttons)))
                        ok(click.answered, "every button press must be answered")
            await t.next_phase()
        row = await t.match()
        ok(row["phase"] in ("finished", "cancelled"), f"size {size}: game did not end (phase {row['phase']})")
        alive_roles = [roles[uid] for uid in await t.alive()]
        if row["phase"] == "finished":
            ok(row["winner"] == rules.winner(alive_roles), f"size {size}: winner {row['winner']} vs alive {alive_roles}")
        ok(row["pending_event_json"] is None, f"size {size}: undelivered event left behind")
        role_cards = [sum("Партия Мафии" in m.text for m in h.dm(u)) for u in t.users]
        ok(role_cards == [1] * size, f"size {size}: every player gets exactly one role card, got {role_cards}")


async def _chatter_ok(h: Harness, t: Table, user, phase: str, alive: set[int]) -> bool:
    """Say something and compare with the quiet rule: night mutes the living, day mutes the dead."""
    mid = await h.say(user, t.chat, "болтаем")
    is_player = user in t.users
    muted = is_player and ((phase == "night" and user.id in alive) or (phase in ("discussion", "voting") and user.id not in alive))
    return h.is_deleted(t.chat, mid) == muted


@scenario
async def abstainers_outvote_a_lone_accuser(h: Harness) -> None:
    t = await Table.create(h, 5)
    await t.start_with_roles(FIVE)
    u = t.users
    await t.pick(u[1], u[4])
    await t.next_phase()
    await t.press(t.host, "К голосованию", "ОБСУЖДЕНИЕ")
    await t.vote(u[0], u[2])
    for voter in (u[1], u[2], u[3]):
        await t.vote(voter, None)
    await t.next_phase()
    ok(await t.phase() == "night", "nobody was eliminated, the game goes on")
    ok("никто не выбыл" in h.world.last(t.chat, "Итог голосования").text, "one accusation against three abstentions removes nobody")
