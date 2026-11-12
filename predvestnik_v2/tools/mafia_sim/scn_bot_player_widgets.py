"""Whole-bot scenarios: widgets for players (S30b) — «Табло» in place of the text plan, every tab against the real
services, claims, «Текстом», text mode, «Сапёр» played to the end, links from a group, the players' switch.

The players' switch (system flag widgets_players_v1) is off by default: without it the same commands answer with
the old text, and only the creator gets widgets.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_util import last_message, said, say


async def _flag(h: Harness, key: str, on: bool) -> None:
    await h.sql("INSERT INTO predvestnik.system_flags(key, enabled, label) VALUES ($1, $2, $1) "
                "ON CONFLICT (key) DO UPDATE SET enabled = EXCLUDED.enabled", key, int(on))


@asynccontextmanager
async def flags(h: Harness, **values: bool):
    before = {r["key"]: r["enabled"] for r in await h.sql("SELECT key, enabled FROM predvestnik.system_flags WHERE key = ANY($1::text[])",
                                                         list(values))}
    for key, on in values.items():
        await _flag(h, key, on)
    try:
        yield
    finally:
        for key in values:
            if key in before:
                await _flag(h, key, bool(before[key]))
            else:
                await h.sql("DELETE FROM predvestnik.system_flags WHERE key = $1", key)


def _widget_sent(h: Harness, user, start: int) -> tuple[int, dict] | None:
    for name, params in h.world.calls[start:]:
        if name == "SendWidget" and int(params["chat_id"]) == user.id:
            mid = max(m for (chat, m) in h.world.widgets if chat == user.id)
            return mid, h.world.widgets[(user.id, mid)]
    return None


def _answer(got: dict) -> dict:
    return json.loads(got["data"]) if got.get("data") else {}


async def _player(h: Harness, name: str):
    """A player who already plays (has an account row, as after the Mini App or a group) and opened the DM."""
    user = h.user(name)
    await h.sql("INSERT INTO predvestnik.users(user_tg_id) VALUES ($1) ON CONFLICT DO NOTHING", user.id)
    await say(h, user, user.id, "/start")
    return user


@bot_scenario
async def widget_pult_replaces_plan_for_players(h: Harness) -> None:
    player = await _player(h, "Табло")
    async with flags(h, widgets_players_v1=False):
        start = len(h.world.calls)
        reply = said(await say(h, player, player.id, "план"))
        ok(_widget_sent(h, player, start) is None and "План дня" in reply, f"switch off: the old text plan: {reply!r}")
    async with flags(h, widgets_players_v1=True):
        start = len(h.world.calls)
        await say(h, player, player.id, "план")
        found = _widget_sent(h, player, start)
        ok(found is not None, "switch on: «план» sends the pult")
        mid, widget = found
        state = json.loads(widget["chat_data"])
        ok(state.get("v") == "day" and state.get("l") and state.get("k") == "", f"the day tab, signed with no skin: {state}")
        ok("var L=" in widget["html"], "the widget is dressed in the player's look when sent")
        ok(widget["allow_queries"], "the pult asks the bot")
        card = h.world.messages[(player.id, mid)]
        labels = [b.get("text") for b in card.buttons()]
        ok(any("Текстом" in t for t in labels), f"every pult has the text fallback button: {labels}")

        for view in ("day", "me", "q", "qw", "pass", "pets"):
            got = _answer(await h.widget_query(player, mid, f"hub:s:{view}"))
            ok(not got.get("e") and got.get("v") == view and got.get("l"), f"tab {view} renders from the real services: {got}")
        switched = _answer(await h.widget_query(player, mid, "hub:v:pass"))
        ok(switched.get("v") == "pass" and json.loads(h.world.widgets[(player.id, mid)]["chat_data"])["v"] == "pass",
           "a tab switch is saved in the message: after a Telegram restart the same tab is shown")

        claim = _answer(await h.widget_query(player, mid, "hub:p:pass"))
        ok(claim.get("o") or claim.get("e"), f"a pass claim with nothing ready answers in words: {claim}")
        quests = _answer(await h.widget_query(player, mid, "hub:q:d:day"))
        ok(quests.get("e") or quests.get("o"), f"an unfinished quest reward is refused in words, not crashed: {quests}")
        dust = _answer(await h.widget_query(player, mid, "hub:d:day"))
        again = _answer(await h.widget_query(player, mid, "hub:d:day"))
        ok(dust.get("o") or dust.get("e"), f"the starfall answers: {dust}")
        if dust.get("o") and "пыли" in dust["o"] and "уже" not in dust["o"]:
            ok("уже" in again.get("o", ""), f"the second catch of the day gives nothing new: {again}")
        gift = _answer(await h.widget_query(player, mid, "hub:g:day"))
        ok("1000" in gift.get("o", "") and not any(r.get("a") == "g" for r in gift["l"]),
           f"the daily gift is paid once and its row leaves the day: {gift}")
        twice = _answer(await h.widget_query(player, mid, "hub:g:day"))
        ok(twice.get("e") and "1000" not in twice.get("o", ""), f"the second tap pays nothing: {twice}")
        chips = await h.sql("SELECT chips FROM predvestnik.casino_v1_wallets WHERE user_id = $1", player.id)
        ok([r["chips"] for r in chips] == [1000], f"exactly one gift on the wallet: {chips}")
        async with flags(h, pets_v2=True):
            pets = _answer(await h.widget_query(player, mid, "hub:s:pets"))
            ok(pets["l"][0]["t"] == "Пока нет питомцев", f"a player without pets gets the way to the first one: {pets}")
        stale = _answer(await h.widget_query(player, mid, "hub:zz:day"))
        ok("устарел" in stale.get("e", ""), f"an unknown action is refused: {stale}")

        before = len(h.world.calls)
        await h.click(player, player.id, h.world.messages[(player.id, mid)], "Текстом")
        text = said([(n, p) for n, p in h.world.calls[before:] if n == "SendMessage"])
        ok("План дня" in text, f"«Текстом» sends the same screen as a message: {text!r}")
        plain = last_message(h, player.id, "План дня")
        ok(any("Всегда текстом" in b.get("text", "") for b in plain.buttons()), "the text copy offers the text mode")
        await h.click(player, player.id, plain, "Всегда текстом")
        start = len(h.world.calls)
        reply = said(await say(h, player, player.id, "квесты"))
        ok(_widget_sent(h, player, start) is None and "КВЕСТЫ" in reply, f"text mode keeps the old texts: {reply!r}")
        start = len(h.world.calls)
        await say(h, player, player.id, "табло")
        ok(_widget_sent(h, player, start) is not None, "«табло» brings the widgets back")
        start = len(h.world.calls)
        await say(h, player, player.id, "пропуск")
        found = _widget_sent(h, player, start)
        ok(found is not None and json.loads(found[1]["chat_data"])["v"] == "pass", "«пропуск» opens the pult on its tab")


@bot_scenario
async def widget_pult_follows_the_skin(h: Harness) -> None:
    from core.widgets import skin
    from infrastructure.repositories import skins_v3
    from tools.mafia_sim.scn_bot_widgets import database
    player = await _player(h, "Образ")
    async with database() as db:
        await skins_v3.ensure_tables(db)
    await h.sql("INSERT INTO predvestnik.skins_v3_owned(user_id, skin_id, tier) VALUES ($1, 'void', 'S') "
                "ON CONFLICT DO NOTHING", player.id)
    await h.sql("INSERT INTO predvestnik.skins_v3_equipped(user_id, skin_id) VALUES ($1, 'void') "
                "ON CONFLICT (user_id) DO UPDATE SET skin_id = 'void'", player.id)
    async with flags(h, widgets_players_v1=True):
        start = len(h.world.calls)
        await say(h, player, player.id, "план")
        mid, widget = _widget_sent(h, player, start)
        dressed = skin.look("void", "S")
        ok(dressed.css in widget["html"] and dressed.data in widget["html"], "the board wears the equipped skin as a whole")
        ok(json.loads(widget["chat_data"])["k"] == "void:S", "and is signed with it")
        await h.sql("DELETE FROM predvestnik.skins_v3_equipped WHERE user_id = $1", player.id)
        fresh = _answer(await h.widget_query(player, mid, "hub:s:me"))
        ok(fresh["k"] == "", f"taking the skin off changes the signature the board compares with: {fresh.get('k')}")
        start = len(h.world.calls)
        await say(h, player, player.id, "табло")
        ok(skin.look(None).css in _widget_sent(h, player, start)[1]["html"], "a new board comes without the skin")


@bot_scenario
async def widget_mines_is_played_to_the_end(h: Harness) -> None:
    player = await _player(h, "Сапёр")
    async with flags(h, widgets_players_v1=True, game_minesweeper_v2=True):
        start = len(h.world.calls)
        await say(h, player, player.id, "сапёр")
        found = _widget_sent(h, player, start)
        ok(found is not None, "«сапёр» sends the board")
        mid, widget = found
        ok(json.loads(widget["chat_data"])["st"] in ("n", "a", "f"), "a fresh widget offers a game")
        state = _answer(await h.widget_query(player, mid, "mines:n:easy"))
        ok(state.get("st") == "f" and state.get("z") == 6 and set(state["b"]) == {"#"}, f"a new easy board: {state}")
        moves = 0
        while state.get("st") in ("f", "a") and moves < 40:
            cell = state["b"].index("#")
            state = _answer(await h.widget_query(player, mid, f"mines:o:{state['x']}:{cell}:{state['v']}"))
            ok(not state.get("e"), f"every move is answered: {state}")
            moves += 1
        ok(state.get("st") in ("w", "l") and state.get("o"), f"the game ends with a result line: {state}")
        ok("*" not in state["b"] or state["st"] == "l", "mines are shown only after a loss")
        saved = json.loads(h.world.widgets[(player.id, mid)]["chat_data"])
        ok(saved.get("st") == state["st"], "the final board is saved in the message")
        old = _answer(await h.widget_query(player, mid, f"mines:o:{state['x']}:0:{state['v']}"))
        ok(old.get("o") and old.get("st") in ("w", "l"), f"a move after the end is refused in words: {old}")
        rows = await h.sql("SELECT status FROM predvestnik.minesweeper_v2_runs WHERE user_id = $1", player.id)
        ok([r["status"] for r in rows] == [state["st"].replace("w", "won").replace("l", "lost")],
           f"the same server run as the Mini App: {rows}")
        again = _answer(await h.widget_query(player, mid, "mines:n:easy"))
        blind = _answer(await h.widget_query(player, mid, f"mines:o:{state['x']}:0:{again['v']}"))
        ok("обновилось" in blind.get("o", "") and blind.get("v") == again["v"] and blind.get("x") == again["x"],
           f"a tap from an older board never lands blind in the new run: {blind}")

    async with flags(h, widgets_players_v1=True, game_minesweeper_v2=False):
        reply = said(await say(h, player, player.id, "сапёр"))
        ok("закрыт" in reply, f"a closed Minesweeper says so: {reply!r}")
        closed = _answer(await h.widget_query(player, mid, "mines:n:easy"))
        ok("закрыт" in closed.get("e", ""), f"and the old widget refuses moves: {closed}")


@bot_scenario
async def widget_links_from_a_group(h: Harness) -> None:
    player = await _player(h, "Группа")
    chat = h.new_chat([player])
    async with flags(h, widgets_players_v1=True, game_minesweeper_v2=True):
        await say(h, player, chat, "бот сапёр")
        reply = last_message(h, chat, "Сапёр")
        links = [b.get("url", "") for b in reply.buttons()]
        ok(any(link.endswith("?start=w-mines") for link in links), f"the group gets a link into the DM: {links}")
        await say(h, player, chat, "бот план")
        plan = last_message(h, chat, "План дня")
        ok(any("start=w-hub-day" in b.get("url", "") for b in plan.buttons()), "«бот план» in a group links to the pult")
        start = len(h.world.calls)
        await say(h, player, player.id, "/start w-hub-pass")
        found = _widget_sent(h, player, start)
        ok(found is not None and json.loads(found[1]["chat_data"])["v"] == "pass", "the link opens the pult on its tab")
    async with flags(h, widgets_players_v1=False):
        start = len(h.world.calls)
        reply = said(await say(h, player, player.id, "/start w-mines"))
        ok(_widget_sent(h, player, start) is None and "Сапёр" in reply, f"without the switch the link answers with text: {reply!r}")


@bot_scenario
async def widget_track_finds_the_cache(h: Harness) -> None:
    from core import pets_v2 as pet_rules
    from infrastructure.repositories import pets_v2 as pets_repo
    from tools.mafia_sim.scn_bot_widgets import database
    player = await _player(h, "Следопыт")
    async with database() as db:
        await pets_repo.ensure_tables(db)
    species = next(iter(pet_rules.SPECIES))
    pet = (await h.sql("INSERT INTO predvestnik.pets(owner_id,name,species_id,rarity) VALUES ($1,'Рыжик',$2,'common') RETURNING id",
                       player.id, species))[0]["id"]
    async with flags(h, widgets_players_v1=True, pets_v2=True):
        start = len(h.world.calls)
        await say(h, player, player.id, "выслеживание")
        found = _widget_sent(h, player, start)
        ok(found is not None, "«выслеживание» in the DM sends the field")
        mid, widget = found
        first = json.loads(widget["chat_data"])
        ok(first["st"] == "n" and first["p"] and first["p"][0][0] == pet, f"a fresh day offers the pet: {first}")
        state = _answer(await h.widget_query(player, mid, f"track:b:{pet}"))
        ok(state.get("st") == "o" and state["c"].count("?") == 6 and "f" not in state["c"], f"three clues, the cache hidden: {state}")
        hidden = (await h.sql("SELECT hidden FROM predvestnik.pet_v2_tracks WHERE user_id=$1", player.id))[0]["hidden"]
        wrong = next(i for i, c in enumerate(state["c"]) if c == "?" and i != hidden)
        again = _answer(await h.widget_query(player, mid, f"track:o:{state['i']}:{wrong}"))
        twice = _answer(await h.widget_query(player, mid, f"track:o:{state['i']}:{wrong}"))
        ok(again["pt"] == state["pt"] - 1 and twice.get("pt") == again["pt"], f"a repeated tap spends attention once: {again} / {twice}")
        won = _answer(await h.widget_query(player, mid, f"track:o:{state['i']}:{hidden}"))
        ok(won.get("st") == "w" and won["c"][hidden] == "f" and "Тайник найден" in won.get("o", ""), f"the cache is found: {won}")
        ok(won.get("a") == pet_rules.TRACK_DAILY - 1 and won.get("p"), "one attempt left and the pet offered again")
        ok(json.loads(h.world.widgets[(player.id, mid)]["chat_data"])["st"] == "w", "the result stays in the message")
