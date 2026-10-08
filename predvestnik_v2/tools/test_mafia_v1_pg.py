#!/usr/bin/env python3
"""Real PostgreSQL proof for Mafia service invariants (lobby, phases, gate, receipts).

The end-to-end Telegram flows live in tools/test_mafia_v1_sim_pg.py; this file pins the
service layer inside one rolled-back transaction.
"""
from __future__ import annotations

import argparse
import asyncio
from types import SimpleNamespace
from urllib.parse import urlparse

import asyncpg

from bot.handlers.mafia_card_views import phase_keyboard, phase_text
from bot.handlers.mafia_cards import publish_phase
from bot.handlers.mafia_delivery import deliver_for_match
from bot.handlers.mafia_dm import send_role_cards
from bot.handlers.mafia_views import lobby_text, settings_keyboard
from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import achievements_v1 as achievements_repo
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import mafia_v1 as repo
from services import mafia_v1 as mafia


class FakeBot:
    """A deterministic Telegram transport for the four-player integration test."""

    def __init__(self):
        self.sent: list[dict] = []
        self.edits: list[dict] = []

    async def me(self):
        return SimpleNamespace(id=1, username="sim_bot")

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append({"chat_id": int(chat_id), "text": text, **kwargs})
        return SimpleNamespace(message_id=9000 + len(self.sent))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": text, **kwargs})

    async def edit_message_reply_markup(self, **kwargs):
        return True

    async def delete_message(self, *args, **kwargs):
        return True


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def expire(db, match_id: int) -> None:
    await db.execute("UPDATE mafia_v1_matches SET phase_deadline=CLOCK_TIMESTAMP()-INTERVAL '1 second' WHERE id=?", (match_id,))


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await achievements_repo.ensure_tables(db)
    await economy_ledger.ensure_tables(db)
    await repo.ensure_tables(db)
    transaction = connection.transaction(); await transaction.start()
    try:
        await check_lobby(db)
        await check_game(db)
    finally:
        await transaction.rollback(); await connection.close()


async def check_lobby(db) -> None:
    try:
        await mafia.create_lobby(db, chat_id=-998876, topic_id=None, initiator_id=7001, username="bad", display_name="Bad", max_players=3)
    except mafia.MafiaConflict as exc:
        assert "4 до 20" in str(exc), "invalid lobby settings must be human-readable"
    else:
        raise AssertionError("invalid lobby size must fail before it creates a match")
    view = await mafia.create_lobby(db, chat_id=-998877, topic_id=None, initiator_id=7101, username="one", display_name="One", max_players=4)
    assert view["roles_auto"] and view["max_players"] == 4
    for user_id, name in ((7102, "Two"), (7103, "Three"), (7104, "Four")):
        view = await mafia.join_lobby(db, match_id=view["match_id"], chat_id=-998877, topic_id=None,
                                      user_id=user_id, username=name.lower(), display_name=name)
    assert len(view["players"]) == 4 and "Что делать" in lobby_text(view)
    try:
        await mafia.join_lobby(db, match_id=view["match_id"], chat_id=-998877, topic_id=None, user_id=7105, username="x", display_name="Five")
    except mafia.MafiaConflict as exc:
        assert "Настройки" in str(exc), "a full lobby must say where to add seats"
    else:
        raise AssertionError("a full lobby must refuse a fifth player")
    view = await mafia.change_settings(db, match_id=view["match_id"], chat_id=-998877, topic_id=None, actor_id=7101,
                                       max_players=6, enabled_roles=("doctor",), vote_mode="open")
    assert view["max_players"] == 6 and view["enabled_roles"] == ("doctor",) and view["vote_mode"] == "open" and not view["roles_auto"]
    rows = [len(row) for row in settings_keyboard(view).inline_keyboard]
    assert rows == [2, 2, 1, 1, 1, 1, 1], f"settings menu shape changed: {rows}"
    assert [len(row) for row in settings_keyboard(view, "players").inline_keyboard] == [4, 3, 1]
    for kwargs in ({"topic_id": 42, "actor_id": 7102}, {"topic_id": None, "actor_id": 7102}):
        try:
            await mafia.change_settings(db, match_id=view["match_id"], chat_id=-998877, max_players=6, enabled_roles=(), vote_mode="secret", **kwargs)
        except mafia.MafiaError:
            continue
        raise AssertionError("a foreign player or topic must not change the lobby")
    try:
        await mafia.create_lobby(db, chat_id=-998877, topic_id=None, initiator_id=7199, username=None, display_name="Dup", max_players=4)
    except mafia.MafiaConflict:
        pass
    else:
        raise AssertionError("one active Mafia match per chat/topic is mandatory")
    await mafia.cancel_match(db, chat_id=-998877, topic_id=None, actor_id=7101)


async def check_game(db) -> None:
    view = await mafia.create_lobby(db, chat_id=-998878, topic_id=None, initiator_id=7101, username="one", display_name="One", max_players=4)
    match_id = view["match_id"]
    for user_id, name in ((7102, "Two"), (7103, "Three"), (7104, "Four")):
        await mafia.join_lobby(db, match_id=match_id, chat_id=-998878, topic_id=None, user_id=user_id, username=name.lower(), display_name=name)
    try:
        await mafia.start_match(db, match_id=match_id, chat_id=-998878, actor_id=7102)
    except mafia.MafiaForbidden:
        pass
    else:
        raise AssertionError("only the host starts")
    # Regression: no stored «Я готов» flag may be required — reachability is checked live by the bot.
    view, roles = await mafia.start_match(db, match_id=match_id, chat_id=-998878, actor_id=7101)
    assert view["phase"] == "night" and len(roles) == 4
    bot = FakeBot()
    assert not await send_role_cards(bot, db, view, chat_title="T"), "all four virtual players receive a role"
    assert {m["chat_id"] for m in bot.sent} == set(roles), "a citizen gets a role card too"
    assert await publish_phase(bot, db, view, gap=0)
    card_count = len(bot.sent)
    refreshed = await mafia.current_view(db, match_id=match_id)
    assert refreshed and refreshed["phase_message_id"]
    assert await publish_phase(bot, db, refreshed, gap=0) and len(bot.sent) == card_count and len(bot.edits) == 1, "refresh edits, never duplicates"
    await mafia.pause_match(db, match_id=match_id, reason="private_action_delivery_failed", detail="Two")
    paused = await mafia.current_view(db, match_id=match_id)
    assert paused["phase"] == "paused" and "Two" in phase_text(paused) and phase_keyboard(paused)
    try:
        await mafia.resume_match(db, chat_id=-998878, topic_id=None, actor_id=7999)
    except mafia.MafiaForbidden:
        pass
    else:
        raise AssertionError("only the host or an admin may resume")
    await db.execute("UPDATE chat_settings SET is_purging=TRUE WHERE chat_id=?", (-998878,))
    try:
        await mafia.resume_match(db, chat_id=-998878, topic_id=None, actor_id=7101)
    except mafia.MafiaConflict as exc:
        assert "чистки" in str(exc)
    else:
        raise AssertionError("an active purge must block resume")
    await db.execute("UPDATE chat_settings SET is_purging=FALSE WHERE chat_id=?", (-998878,))
    view = await mafia.resume_match(db, chat_id=-998878, topic_id=None, actor_id=7999, is_admin=True)
    assert view["phase"] == "night" and view["phase_deadline"], "an admin resumes with the remaining timer"
    await check_gate_and_votes(db, match_id, roles, bot)


async def check_gate_and_votes(db, match_id: int, roles: dict[int, str], bot: FakeBot) -> None:
    gate = lambda uid: mafia.message_gate(db, chat_id=-998878, topic_id=None, user_id=uid)  # noqa: E731
    assert await gate(7101) == "suppress", "a living player is quiet at night"
    assert await gate(7999) == "allow", "an onlooker is never silenced"
    town = next(uid for uid, role in roles.items() if role == "citizen")
    await repo.kill_player(db, match_id=match_id, user_id=town)
    assert await gate(town) == "allow", "the dead may talk at night, the living may not hear their plans"
    living = next(uid for uid in roles if uid != town)
    try:
        await mafia.start_match(db, match_id=match_id, chat_id=-998878, actor_id=7101)
    except mafia.MafiaConflict:
        pass
    else:
        raise AssertionError("double start must not redraw roles")
    await expire(db, match_id)
    night = await mafia.advance_due_match(db, match_id=match_id)
    assert night and night["view"]["phase"] == "discussion"
    assert await mafia.advance_due_match(db, match_id=match_id) is None, "a phase closes exactly once"
    await deliver_for_match(bot, db, match_id)
    assert any(m["chat_id"] == -998878 and "Рассвет" in m["text"] for m in bot.sent), "the result is announced in the group"
    assert await gate(living) == "allow" and await gate(town) == "suppress" and await gate(7999) == "allow"
    await expire(db, match_id)
    voting = (await mafia.advance_due_match(db, match_id=match_id))["view"]
    assert voting["phase"] == "voting"
    alive = [p["user_id"] for p in voting["players"] if p["alive"]]
    number = voting["phase_number"]
    for target in (alive[1], alive[2]):  # a changed vote replaces the first
        await mafia.submit_action(db, match_id=match_id, chat_id=-998878, user_id=alive[0], phase_number=number,
                                  action_type="vote", target_user_id=target)
    await db.execute("UPDATE mafia_v1_matches SET vote_mode='open' WHERE id=?", (match_id,))
    open_view = await mafia.current_view(db, match_id=match_id)
    assert open_view["open_votes"] and open_view["votes_cast"] == 1 and open_view["votes_needed"] == len(alive)
    await db.execute("UPDATE mafia_v1_matches SET vote_mode='secret' WHERE id=?", (match_id,))
    assert "open_votes" not in await mafia.current_view(db, match_id=match_id), "secret voting must not leak selections"
    for bad_user in (7999,):
        try:
            await mafia.submit_action(db, match_id=match_id, chat_id=-998878, user_id=bad_user, phase_number=number,
                                      action_type="vote", target_user_id=alive[1])
        except mafia.MafiaForbidden:
            continue
        raise AssertionError("a non-player must not vote")
    try:
        await mafia.cancel_match(db, chat_id=-998878, topic_id=None, actor_id=7999)
    except mafia.MafiaForbidden:
        pass
    else:
        raise AssertionError("only the host or an admin cancels")
    await check_finish(db, match_id, roles)


async def check_finish(db, match_id: int, roles: dict[int, str]) -> None:
    await db.execute("UPDATE mafia_v1_players SET alive=FALSE WHERE match_id=? AND role!='mafia'", (match_id,))
    await db.execute("UPDATE mafia_v1_matches SET phase='night',phase_deadline=CLOCK_TIMESTAMP()-INTERVAL '1 second' WHERE id=?", (match_id,))
    done = await mafia.advance_due_match(db, match_id=match_id)
    assert done and done["view"]["phase"] == "finished" and done["view"]["roles_reveal"], "the end reveals every role"
    assert await mafia.record_terminal_rewards(db, match_id=match_id), "receipts are issued after the phase has committed"
    assert await mafia.record_terminal_rewards(db, match_id=match_id), "and a retry changes nothing"
    count = lambda metric: db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE metric=? AND event_id=?", (metric, f"mafia:{match_id}"))  # noqa: E731
    for metric, expected in (("mafia_completed", 4), ("game_completed", 4), ("mafia_win", sum(r in ("mafia", "don") for r in roles.values()))):
        async with count(metric) as cursor:
            assert (await cursor.fetchone())[0] == expected, f"{metric} receipts"
    assert await mafia.advance_due_match(db, match_id=match_id) is None
    history = await mafia.player_history(db, user_id=7101)
    assert history["matches"] and history["matches"][0]["role"] == roles[7101], "history exposes only the player's own role"


parser = argparse.ArgumentParser(); parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args(); asyncio.run(run(args.dsn))
print("mafia_v1: service invariants, gate, votes and receipts OK")
