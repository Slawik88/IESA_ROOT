"""Scenario: a first-time player must understand every screen (copy lint over a whole game)."""
from __future__ import annotations

import re

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import ok, scenario
from tools.mafia_sim.table import Table
from tools.mafia_sim.world import parse_html

EIGHT = ["citizen", "mafia", "don", "doctor", "detective", "citizen", "citizen", "citizen"]
JARGON = ("фракци", "тай-брейк", "state_version", "callback", "match_id", "phase", "payload", "ruleset")
REVEAL = re.compile(r"\d+\. [^\n]+ — [🔫🎩💉🔎🧑]")
PHASE = re.compile(r"НОЧЬ|ОБСУЖДЕНИЕ|ГОЛОСОВАНИЕ|ПАУЗЕ")


async def _play_to_the_end(h: Harness) -> Table:
    t = await Table.create(h, 8, command="бот мафия 8 дон доктор детектив")
    await t.start_with_roles(EIGHT)
    u = t.users
    for actor, target in ((1, 5), (2, 5), (3, 0), (4, 1)):
        await t.pick(u[actor], u[target])
    await t.next_phase()
    await t.press(t.host, "К голосованию", "ОБСУЖДЕНИЕ")
    for index in await _alive_indexes(t):
        await t.vote(u[index], u[1])
    await t.next_phase()
    for actor, target in ((2, 7), (3, 0), (4, 2)):
        await t.pick(u[actor], u[target])
    await t.next_phase()
    await t.next_phase()
    for index in await _alive_indexes(t):
        await t.vote(u[index], u[2] if index != 2 else u[0])
    await t.next_phase()
    return t


async def _alive_indexes(t: Table) -> list[int]:
    alive = await t.alive()
    return [i for i, user in enumerate(t.users) if user.id in alive]


@scenario
async def newbie_copy_lint(h: Harness) -> None:
    t = await _play_to_the_end(h)
    ok(await t.phase() == "finished", f"the scripted game must reach the end: {await t.phase()}")
    sent = [(name, params) for name, params in h.world.calls if name in ("SendMessage", "EditMessageText") and params.get("text")]
    ok(len(sent) > 40, f"a full game should have produced many messages, got {len(sent)}")
    finale = False
    for name, params in sent:
        plain = parse_html(params["text"])[0] if params.get("parse_mode") == "HTML" else params["text"]
        markup = params.get("reply_markup")
        group = int(params["chat_id"]) < 0
        low = plain.lower()
        ok(not [w for w in JARGON if w in low], f"developer jargon in a player-facing text: {plain[:80]!r}")
        if group and PHASE.search(plain) and markup is not None and "Остановить игру?" not in plain:
            ok("Что делать" in plain, f"every game card tells the player what to do: {plain[:70]!r}")
        if "набор игроков" in plain:
            ok("Что делать" in plain and "Как играть" in str(markup), "the lobby explains itself and links the rules")
        if "Партия Мафии" in plain and not group:
            ok("Цель:" in plain and "Что делать:" in plain, f"a role card states goal and actions: {plain[:70]!r}")
        if "победил" in low and "Кто кем был" in plain:
            finale = True
        elif group and "Кто кем был" not in plain and "МАФИЯ НАЧАЛАСЬ" not in plain:
            ok(not REVEAL.search(plain) and "(Дон)" not in plain, f"roles must stay secret in the group until the end: {plain[:80]!r}")
        for row in (markup.inline_keyboard if markup else []):
            for button in row:
                ok(len(button.text) <= 40, f"a button label that long is hard to read on a phone: {button.text!r}")
    ok(finale, "the final message reveals everybody's role")
