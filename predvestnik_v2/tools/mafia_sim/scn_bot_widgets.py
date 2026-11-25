"""Whole-bot scenarios: HTML widgets (Bot API 10.4, S30) — sending to the creator's DM, taps, refusals, faults.

The bot must answer every widget query (Telegram shows «бот не ответил» after 15 s), keep unrelated updates
working when a widget handler crashes, and never act for someone who is not allowed to use the widget.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager, contextmanager

from tools.mafia_sim.harness import Harness
from tools.mafia_sim.registry import bot_scenario, ok
from tools.mafia_sim.scn_bot_util import said, say
from tools.mafia_sim.world import TgError


@asynccontextmanager
async def database():
    from infrastructure.database import get_pool
    from infrastructure.pg_adapter import PGAdapter
    async with get_pool().acquire() as conn:
        yield PGAdapter(conn)


@contextmanager
def creator_is(user_id: int):
    """The creator of the bot is DEVELOPER_ID; the scenario makes its own sim user the creator for a while."""
    from bot.config import config
    before = config.developer_id
    object.__setattr__(config, "developer_id", int(user_id))
    try:
        yield
    finally:
        object.__setattr__(config, "developer_id", before)


async def _send(h: Harness, user, key: str) -> int:
    from services import widgets
    async with database() as db:
        message = await widgets.send(h.bot, db, user.id, key)
    return message.message_id


def _answer(got: dict) -> dict:
    return json.loads(got["data"]) if got.get("data") else {}


@bot_scenario
async def widgets_are_requested_from_telegram(h: Harness) -> None:
    from bot.dispatcher import allowed_updates
    from core import widgets
    asked = allowed_updates(h.dp)
    ok(set(widgets.UPDATE_TYPES) <= set(asked), f"polling must ask Telegram for widget queries: {asked}")
    ok(set(h.dp.resolve_used_update_types()) <= set(asked), "and still for everything the handlers need")


@bot_scenario
async def widget_creator_plays_tic_tac_toe(h: Harness) -> None:
    from services.widgets import ttt
    ttt._rng.seed(7)
    owner = h.user("Создатель")
    with creator_is(owner.id):
        message_id = await _send(h, owner, "ttt")
        sent = h.world.widgets[(owner.id, message_id)]
        ok(sent["allow_queries"] and json.loads(sent["chat_data"])["b"] == "-" * 9, f"a fresh board is sent: {sent}")
        ok(h.world.api("SendWidget")[-1]["caption"], "every widget has a caption (old Telegram apps show only it)")

        fresh = _answer(await h.widget_query(owner, message_id, "ttt:s"))
        ok(fresh.get("b") == "-" * 9 and fresh.get("r"), f"a background refresh returns the board: {fresh}")

        moved = _answer(await h.widget_query(owner, message_id, "ttt:m:4:" + "-" * 9))
        board = moved.get("b", "")
        ok(board[4] == "x" and board.count("o") == 1 and board.count("x") == 1, f"the move and the bot's reply: {moved}")
        ok(json.loads(h.world.widgets[(owner.id, message_id)]["chat_data"])["b"] == board, "the board is saved in the message")

        taken = _answer(await h.widget_query(owner, message_id, f"ttt:m:4:{board}"))
        ok("занята" in taken.get("e", ""), f"an occupied cell is refused: {taken}")
        forged = _answer(await h.widget_query(owner, message_id, "ttt:m:0:xxxx-----"))
        ok(taken.get("e") and forged.get("e"), f"an impossible board is refused: {forged}")


@bot_scenario
async def widget_refuses_strangers_garbage_and_wallet(h: Harness) -> None:
    owner, stranger = h.user("Создатель"), h.user("Игрок")
    with creator_is(owner.id):
        message_id = await _send(h, owner, "ping")
        alien = _answer(await h.widget_query(stranger, message_id, "ping:s"))
        ok("только создателю" in alien.get("e", ""), f"a widget of the creator does not answer other players: {alien}")
        junk = _answer(await h.widget_query(owner, message_id, "nope:zz"))
        ok("устарел" in junk.get("e", ""), f"unknown data is refused politely: {junk}")
        wallet = _answer(await h.widget_query(owner, message_id, "ping:s", kind="sign_data"))
        ok("кошельком" in wallet.get("e", ""), f"wallet queries are not supported yet: {wallet}")
        chat = h.new_chat([owner])
        group = _answer(await h.widget_query(owner, message_id, "ping:s", chat_id=chat))
        ok("только в личке" in group.get("e", ""), f"a widget outside the DM is refused: {group}")
        fine = _answer(await h.widget_query(owner, message_id, "ping:s"))
        ok(fine.get("t") and not fine.get("e"), f"the creator still gets a normal answer: {fine}")


@bot_scenario
async def widget_crash_is_answered_and_bot_keeps_working(h: Harness) -> None:
    from services.widgets import ping
    owner = h.user("Создатель")
    with creator_is(owner.id):
        message_id = await _send(h, owner, "ping")
        original = ping.state

        async def broken(db, user_id):
            raise RuntimeError("simulated widget bug")
        ping.state = broken
        try:
            crashed = _answer(await h.widget_query(owner, message_id, "ping:s"))
        finally:
            ping.state = original
        ok("Что-то пошло не так" in crashed.get("e", ""), f"a crash inside a widget still gets an answer: {crashed}")

        h.world.fail(lambda name, params: name == "AnswerWidgetQuery", TgError(400, "Bad Request: query is too old"))
        await h._feed({"widget_query": {"id": "late-1", "from": owner.json(), "chat": h._chat_json(owner.id, owner),
                                        "message_id": message_id, "chat_instance": "sim", "type": {"type": "data"}, "data": "ping:s"}})
        reply = said(await say(h, owner, owner.id, "баланс"))
        ok(reply.strip(), f"after a failed answer the bot still handles ordinary messages: {reply!r}")


@bot_scenario
async def widget_switch_turns_widgets_off(h: Harness) -> None:
    from services import feature_switches, widgets
    owner = h.user("Создатель")
    with creator_is(owner.id):
        message_id = await _send(h, owner, "ping")
        async with database() as db:
            await feature_switches.set_switch(db, 0, "group:widgets", False, actor_id=owner.id, reason="sim")
        try:
            off = _answer(await h.widget_query(owner, message_id, "ping:s"))
            ok("выключены" in off.get("e", ""), f"a switched-off widget says so: {off}")
            refused = ""
            try:
                await _send(h, owner, "ping")
            except widgets.Refused as exc:
                refused = str(exc)
            ok("выключены" in refused, f"nothing is sent while widgets are off: {refused!r}")
        finally:
            async with database() as db:
                await feature_switches.set_switch(db, 0, "group:widgets", True, actor_id=owner.id, reason="sim")
        on = _answer(await h.widget_query(owner, message_id, "ping:s"))
        ok(on.get("t"), f"switched back on, the widget answers again: {on}")
