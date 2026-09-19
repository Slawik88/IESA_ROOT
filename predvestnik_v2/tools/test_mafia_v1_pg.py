#!/usr/bin/env python3
"""Real PostgreSQL proof for Mafia lobby, phase and message-gate invariants."""
from __future__ import annotations

import argparse
import asyncio
from types import SimpleNamespace
from urllib.parse import urlparse

import asyncpg

from infrastructure.pg_adapter import PGAdapter
from infrastructure.repositories import achievements_v1 as achievements_repo
from infrastructure.repositories import economy_ledger
from infrastructure.repositories import mafia_v1 as repo
from services import mafia_v1 as mafia
from bot.handlers.mafia_v1 import _lobby_text, _phase_keyboard, _phase_text, _send_night_prompts, _settings_keyboard, notify_phase_transition, publish_phase


class FakeBot:
    """A deterministic Telegram transport for the four-player integration test."""

    def __init__(self):
        self.sent: list[dict] = []
        self.edits: list[dict] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append({"chat_id": int(chat_id), "text": text, **kwargs})
        return SimpleNamespace(message_id=9000 + len(self.sent))

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": text, **kwargs})


def local_dsn(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise argparse.ArgumentTypeError("only a loopback PostgreSQL DSN is allowed")
    return value


async def run(dsn: str) -> None:
    connection = await asyncpg.connect(dsn)
    db = PGAdapter(connection)
    await achievements_repo.ensure_tables(db)
    await economy_ledger.ensure_tables(db)
    transaction = connection.transaction(); await transaction.start()
    try:
        try:
            await mafia.create_lobby(
                db, chat_id=-998876, topic_id=None, initiator_id=7001, username="bad", display_name="Bad", max_players=3,
            )
        except mafia.MafiaConflict as exc:
            assert "4 до 20" in str(exc), "invalid lobby settings must be human-readable"
        else:
            raise AssertionError("invalid lobby size must fail before it creates a match")
        view = await mafia.create_lobby(
            db, chat_id=-998877, topic_id=None, initiator_id=7101, username="one", display_name="One", max_players=4,
        )
        match_id = view["match_id"]
        for user_id, name in ((7102, "Two"), (7103, "Three"), (7104, "Four")):
            view = await mafia.join_lobby(db, match_id=match_id, chat_id=-998877, topic_id=None,
                                          user_id=user_id, username=name.lower(), display_name=name)
        assert len(view["players"]) == 4
        assert "Что делать" in _lobby_text(view), "the lobby must explain the next action without command documentation"
        view = await mafia.change_settings(
            db, match_id=match_id, chat_id=-998877, topic_id=None, actor_id=7101,
            max_players=6, enabled_roles=("doctor",), vote_mode="open",
        )
        assert view["max_players"] == 6 and view["enabled_roles"] == ("doctor",) and view["vote_mode"] == "open"
        assert [len(row) for row in _settings_keyboard(view).inline_keyboard] == [1, 1, 1, 1], "the main settings screen must remain a readable menu"
        assert [len(row) for row in _settings_keyboard(view, "players").inline_keyboard] == [3, 1], "the player picker must offer a simple previous/current/next control"
        try:
            await mafia.change_settings(
                db, match_id=match_id, chat_id=-998877, topic_id=42, actor_id=7102,
                max_players=6, enabled_roles=(), vote_mode="secret",
            )
        except mafia.MafiaError:
            pass
        else:
            raise AssertionError("a foreign player or topic must not change the lobby")
        try:
            await mafia.create_lobby(db, chat_id=-998877, topic_id=None, initiator_id=7199,
                                     username=None, display_name="Duplicate", max_players=4)
        except mafia.MafiaConflict:
            pass
        else:
            raise AssertionError("one active Mafia match per chat/topic is mandatory")
        try:
            await mafia.start_match(db, match_id=match_id, chat_id=-998877, actor_id=7101)
        except mafia.MafiaConflict as exc:
            assert "Two" in str(exc), "the host must see who still needs to confirm private messages"
        else:
            raise AssertionError("start must fail until every player confirms DM readiness")
        for user_id in (7101, 7102, 7103, 7104):
            await mafia.confirm_dm_ready(db, user_id=user_id)
        view, roles = await mafia.start_match(db, match_id=match_id, chat_id=-998877, actor_id=7101)
        assert view["phase"] == "night" and len(roles) == 4
        bot = FakeBot()
        internal_players = await repo.players(db, match_id=match_id)
        failed = await _send_night_prompts(
            bot, match_id=match_id, phase_number=view["phase_number"], roles_by_user=roles,
            players=internal_players, include_role=True,
        )
        assert not failed, "all four virtual players must receive their private role"
        assert {message["chat_id"] for message in bot.sent} == set(roles), "a citizen must receive a role too"
        await publish_phase(bot, db, view)
        first_phase_card_count = len(bot.sent)
        refreshed = await mafia.current_view(db, match_id=match_id)
        assert refreshed and refreshed["phase_message_id"]
        await publish_phase(bot, db, refreshed)
        assert len(bot.sent) == first_phase_card_count and len(bot.edits) == 1, "timer refresh edits one card, never posts a duplicate"
        await mafia.pause_match(db, match_id=match_id, reason="test_pause")
        paused = await mafia.current_view(db, match_id=match_id)
        assert paused and paused["phase"] == "paused", "a safety pause must persist"
        assert "Продолжить" in _phase_text(paused)
        assert _phase_keyboard(paused), "a paused card must offer visible recovery controls"
        await publish_phase(bot, db, paused)
        assert any("ПАРТИЯ НА ПАУЗЕ" in edit["text"] for edit in bot.edits), "the group card must visibly switch to paused"
        try:
            await mafia.resume_match(db, chat_id=-998877, topic_id=None, actor_id=7999)
        except mafia.MafiaForbidden:
            pass
        else:
            raise AssertionError("only the host may resume a paused game")
        await db.execute("UPDATE chat_settings SET is_purging=TRUE WHERE chat_id=?", (-998877,))
        try:
            await mafia.resume_match(db, chat_id=-998877, topic_id=None, actor_id=7101)
        except mafia.MafiaConflict as exc:
            assert "чистки" in str(exc), "resume must explain why a pause cannot end yet"
        else:
            raise AssertionError("an active purge must block resume")
        await db.execute("UPDATE chat_settings SET is_purging=FALSE WHERE chat_id=?", (-998877,))
        view = await mafia.resume_match(db, chat_id=-998877, topic_id=None, actor_id=7101)
        assert view["phase"] == "night" and view["phase_deadline"], "resume restores the original phase and remaining timer"
        assert await mafia.message_gate(db, chat_id=-998877, topic_id=None, user_id=7101) == "suppress"
        assert await mafia.message_gate(db, chat_id=-998877, topic_id=None, user_id=7999) == "allow"
        town_player = next(user_id for user_id, role in roles.items() if role == "citizen")
        await repo.kill_player(db, match_id=match_id, user_id=town_player)
        assert await mafia.message_gate(db, chat_id=-998877, topic_id=None, user_id=town_player) == "suppress"
        living_player = next(user_id for user_id in roles if user_id != town_player)
        try:
            await mafia.start_match(db, match_id=match_id, chat_id=-998877, actor_id=7101)
        except mafia.MafiaConflict:
            pass
        else:
            raise AssertionError("double start must not redraw roles")
        await db.execute("UPDATE mafia_v1_matches SET phase_deadline=CLOCK_TIMESTAMP()-INTERVAL '1 second' WHERE id=?", (match_id,))
        night = await mafia.advance_due_match(db, match_id=match_id)
        assert night and night["view"]["phase"] == "discussion"
        await notify_phase_transition(bot, db, night)
        assert any(message["chat_id"] == -998877 and "Рассвет" in message["text"] for message in bot.sent), "phase result must be visible in the group"
        assert await mafia.message_gate(db, chat_id=-998877, topic_id=None, user_id=living_player) == "allow"
        assert await mafia.message_gate(db, chat_id=-998877, topic_id=None, user_id=7999) == "suppress"
        await db.execute("UPDATE mafia_v1_matches SET phase_deadline=CLOCK_TIMESTAMP()-INTERVAL '1 second' WHERE id=?", (match_id,))
        voting = await mafia.advance_due_match(db, match_id=match_id)
        assert voting and voting["view"]["phase"] == "voting"
        alive = [player["user_id"] for player in voting["view"]["players"] if player["alive"]]
        await mafia.submit_action(db, match_id=match_id, chat_id=-998877, user_id=alive[0],
                                  phase_number=voting["view"]["phase_number"], action_type="vote", target_user_id=alive[1])
        # A changed vote replaces rather than duplicates the player's action.
        await mafia.submit_action(db, match_id=match_id, chat_id=-998877, user_id=alive[0],
                                  phase_number=voting["view"]["phase_number"], action_type="vote", target_user_id=alive[2])
        open_view = await mafia.current_view(db, match_id=match_id)
        assert open_view and open_view["open_votes"] and open_view["open_votes"][0]["voters"], "open voting must show its current choices"
        await db.execute("UPDATE mafia_v1_matches SET vote_mode='secret' WHERE id=?", (match_id,))
        secret_view = await mafia.current_view(db, match_id=match_id)
        assert secret_view and "open_votes" not in secret_view, "secret voting must not leak selections"
        await db.execute("UPDATE mafia_v1_matches SET vote_mode='open' WHERE id=?", (match_id,))
        try:
            await mafia.submit_action(db, match_id=match_id, chat_id=-998877, user_id=7999,
                                      phase_number=voting["view"]["phase_number"], action_type="vote", target_user_id=alive[1])
        except mafia.MafiaForbidden:
            pass
        else:
            raise AssertionError("non-player must not vote")
        try:
            await mafia.cancel_match(db, chat_id=-998877, topic_id=None, actor_id=7999)
        except mafia.MafiaForbidden:
            pass
        else:
            raise AssertionError("only the lobby creator may cancel a match")
        # End through the authoritative phase resolver, not cancellation: all
        # four seats must receive one terminal quest receipt, including a dead
        # player, and a scheduler retry may not add another.
        await db.execute("UPDATE mafia_v1_players SET alive=FALSE WHERE match_id=? AND role!='mafia'", (match_id,))
        await db.execute("UPDATE mafia_v1_matches SET phase='night',phase_deadline=CLOCK_TIMESTAMP()-INTERVAL '1 second' WHERE id=?", (match_id,))
        completed = await mafia.advance_due_match(db, match_id=match_id)
        assert completed and completed["view"]["phase"] == "finished"
        async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE metric='mafia_completed' AND event_id=?", (f"mafia:{match_id}",)) as cursor:
            assert (await cursor.fetchone())[0] == 4
        async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE metric='game_completed' AND event_id=?", (f"mafia:{match_id}",)) as cursor:
            assert (await cursor.fetchone())[0] == 4
        async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE metric='mafia_win' AND event_id=?", (f"mafia:{match_id}",)) as cursor:
            assert (await cursor.fetchone())[0] == sum(role in ('mafia', 'don') for role in roles.values())
        assert await mafia.advance_due_match(db, match_id=match_id) is None
        async with db.execute("SELECT COUNT(*) FROM quest_v1_metric_receipts WHERE metric='mafia_completed' AND event_id=?", (f"mafia:{match_id}",)) as cursor:
            assert (await cursor.fetchone())[0] == 4
        history = await mafia.player_history(db, user_id=7101)
        assert history["matches"] and history["matches"][0]["role"] == roles[7101], "history exposes only the player's own role"
    finally:
        await transaction.rollback(); await connection.close()


parser = argparse.ArgumentParser(); parser.add_argument("--dsn", required=True, type=local_dsn)
args = parser.parse_args(); asyncio.run(run(args.dsn))
print("mafia_v1: four virtual players, private roles, phase card, gate and votes OK")
