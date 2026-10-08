"""Durable delivery of stored Mafia events and the scheduler pass.

``advance_due_match`` stores what must be announced (dawn, vote result, win, abandonment)
inside the same transaction that moves the phase.  This module delivers it in ordered
steps; every finished step is recorded, so a Telegram hiccup in step 5 never repeats the
dawn message from step 1.  A retry happens on the next tick (every 2 seconds).
"""
from __future__ import annotations

from typing import Awaitable, Callable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from loguru import logger

from bot.handlers import mafia_dm as dm
from bot.handlers.mafia_card_views import (abandoned_text, dawn_text, finished_text, lobby_closed_text,
                                           phase_keyboard, vote_result_text)
from bot.handlers.mafia_cards import publish_phase
from bot.handlers.mafia_filters import bot_username
from core import mafia_v1 as rules
from infrastructure.repositories import mafia_v1 as repo
from infrastructure.repositories import mafia_v1_ops as ops
from infrastructure.repositories import system_flags
from services.formatting import safe_html
from services import mafia_v1 as mafia

MAX_ATTEMPTS = 15
Step = tuple[str, Callable[[], Awaitable[bool]]]


class StopDelivery(Exception):
    """The event was replaced by a newer one (e.g. an abort): stop this one without clearing."""


async def group_say(bot: Bot, view: dict, text: str, markup=None) -> bool:
    """Send to the match's chat/topic.  False = transient failure, retry; True = sent or hopeless."""
    try:
        await bot.send_message(view["chat_id"], text, reply_markup=markup, parse_mode="HTML",
                               message_thread_id=view.get("topic_id"))
    except (TelegramRetryAfter, TelegramNetworkError, TelegramServerError) as exc:
        logger.warning(f"Mafia group message postponed: {exc}")
        return False
    except TelegramAPIError as exc:
        logger.warning(f"Mafia group message dropped: {exc}")
    return True


class PhaseDelivery:
    """Ordered, resumable steps that follow one phase change."""

    def __init__(self, bot: Bot, db, view: dict, event: dict) -> None:
        self.bot, self.db, self.view, self.event = bot, db, view, event

    def steps(self) -> list[Step]:
        return [("announce", self.announce), ("checks", self.checks), ("eliminated", self.eliminated),
                ("strip", self.strip), ("prompts", self.prompts), ("card", self.card), ("final", self.final),
                ("rewards", self.rewards)]

    def _victim(self) -> dict | None:
        uid = self.event.get("eliminated_user_id")
        return next((p for p in self.view["players"] if int(p["user_id"]) == int(uid or 0)), None)

    async def announce(self) -> bool:
        previous = self.event.get("previous_phase")
        if previous == "night":
            return await group_say(self.bot, self.view, dawn_text(self.view, self._victim()))
        if previous == "voting":
            return await group_say(self.bot, self.view, vote_result_text(self._victim()))
        return True

    async def checks(self) -> bool:
        await dm.send_checks(self.bot, self.db, self.view, self.event.get("private_checks", []))
        return True

    async def eliminated(self) -> bool:
        if self.view["phase"] in ("finished", "cancelled"):
            return True  # "you may only watch" is wrong news once the game is over
        await dm.notify_eliminated(self.bot, self.event.get("eliminated_user_id"))
        return True

    async def strip(self) -> bool:
        await dm.strip_old_prompts(self.bot, self.db, match_id=self.view["match_id"], phase_number=self.view["phase_number"])
        return True

    async def prompts(self) -> bool:
        if self.view["phase"] == "voting":
            await dm.send_vote_prompts(self.bot, self.db, self.view)
            return True
        if self.view["phase"] != "night":
            return True
        failed = await dm.send_night_prompts(self.bot, self.db, self.view)
        if failed:
            names = [p["display_name"] for p in self.view["players"] if int(p["user_id"]) in failed]
            await mafia.pause_match(self.db, match_id=self.view["match_id"], reason="private_action_delivery_failed",
                                    detail=", ".join(names)[:300])
            self.view = await mafia.current_view(self.db, match_id=self.view["match_id"]) or self.view
        return True

    async def card(self) -> bool:
        repost = self.event.get("previous_phase") == "discussion" and self.view["phase"] == "voting"
        return await publish_phase(self.bot, self.db, self.view, gap=0, repost=repost)

    async def final(self) -> bool:
        if self.view["phase"] == "finished":
            return await group_say(self.bot, self.view, finished_text(self.view),
                                   phase_keyboard(self.view, await bot_username(self.bot)))
        if self.event.get("abandoned"):
            return await group_say(self.bot, self.view, abandoned_text())
        return True


    async def rewards(self) -> bool:
        """Last on purpose: players see the result even while quests/achievements are unhealthy."""
        if self.view["phase"] != "finished":
            return True
        return await mafia.record_terminal_rewards(self.db, match_id=self.view["match_id"])


class StartDelivery(PhaseDelivery):
    """Roles to every DM, retire the lobby card, post the first night card."""

    def steps(self) -> list[Step]:
        return [("roles", self.roles), ("lobby_card", self.lobby_card), ("card", self.card)]

    async def roles(self) -> bool:
        async with self.db.execute("SELECT chat_title FROM chat_settings WHERE chat_id=?", (self.view["chat_id"],)) as cursor:
            row = await cursor.fetchone()
        failed = await dm.send_role_cards(self.bot, self.db, self.view, chat_title=row[0] if row else None)
        if not failed:
            return True
        names = ", ".join(safe_html(p["display_name"]) for p in self.view["players"] if int(p["user_id"]) in failed)
        await mafia.abort_match(self.db, match_id=self.view["match_id"], reason="private_role_delivery_failed")
        await group_say(self.bot, self.view, f"❌ Партия отменена: роль не дошла до {names}. Пусть откроют бота и нажмут «Старт», "
                                             "затем соберите лобби заново: «бот мафия».")
        raise StopDelivery

    async def lobby_card(self) -> bool:
        message_id = self.view.get("lobby_message_id")
        if message_id:
            roster = " · ".join(f"{p['join_order']}. {safe_html(p['display_name'])}" for p in self.view["players"])
            try:
                await self.bot.edit_message_text(
                    f"🕵️ <b>МАФИЯ НАЧАЛАСЬ</b>\n\nИгроки: {roster}\n\nРоли разосланы в личные сообщения. Сейчас ночь — в чат не пишем.",
                    chat_id=self.view["chat_id"], message_id=message_id, reply_markup=None, parse_mode="HTML")
            except TelegramAPIError as exc:
                logger.debug(f"Mafia lobby card not retired: {exc}")
        return True


class ClosedDelivery(PhaseDelivery):
    """A lobby that timed out, or a match stopped by its host/admin."""

    def steps(self) -> list[Step]:
        return [("lobby_card", self.lobby_card), ("strip", self.strip), ("card", self.card_if_started)]

    async def lobby_card(self) -> bool:
        message_id = self.view.get("lobby_message_id")
        if self.view["phase_number"] == 0 and message_id:
            try:
                await self.bot.edit_message_text(lobby_closed_text(self.view.get("finished_reason") or ""),
                                                 chat_id=self.view["chat_id"], message_id=message_id,
                                                 reply_markup=None, parse_mode="HTML")
            except TelegramAPIError as exc:
                logger.debug(f"Mafia lobby card not updated: {exc}")
        return True

    async def strip(self) -> bool:
        await dm.strip_old_prompts(self.bot, self.db, match_id=self.view["match_id"], phase_number=self.view["phase_number"] + 1)
        return True

    async def card_if_started(self) -> bool:
        if self.view["phase_number"] == 0 or not self.view.get("phase_message_id"):
            return True
        return await publish_phase(self.bot, self.db, self.view, gap=0)


async def deliver_for_match(bot: Bot, db, match_id: int) -> bool:
    """Deliver the stored event of one match.  True when nothing is left to do."""
    event = await ops.claim_event(db, match_id=match_id)
    if event is None:
        return True
    view = await mafia.current_view(db, match_id=match_id)
    if view is None or int(event.get("attempts", 1)) > MAX_ATTEMPTS:
        logger.error(f"Mafia event for match {match_id} abandoned after repeated failures")
        await ops.clear_pending_event(db, match_id=match_id)
        return True
    cls = {"phase": PhaseDelivery, "started": StartDelivery}.get(event.get("kind"), ClosedDelivery)
    delivery = cls(bot, db, view, event)
    done = list(event.get("done", []))
    for name, step in delivery.steps():
        if name in done:
            continue
        try:
            ok = await step()
        except StopDelivery:
            return await deliver_for_match(bot, db, match_id)  # the replacement event (e.g. the abort notice)
        except dm.RetryLater as exc:
            logger.warning(f"Mafia step {name} postponed: {exc}")
            ok = False
        if not ok:
            await ops.release_event(db, match_id=match_id)
            return False
        await ops.mark_event_step(db, match_id=match_id, step=name)
        done.append(name)
    await ops.clear_pending_event(db, match_id=match_id)
    return True


async def notify_phase_transition(bot: Bot, db, event: dict) -> None:
    """Compatibility entry point: deliver whatever is stored for the event's match."""
    await deliver_for_match(bot, db, int(event["match_id"]))


async def _guarded(label: str, coro) -> None:
    try:
        await coro
    except Exception:  # noqa: BLE001 - one broken match must not stall the others
        logger.exception(f"Mafia tick: {label} failed")


async def tick(bot: Bot, db) -> None:
    """One scheduler pass: expire lobbies, close due phases, deliver events, refresh timer cards."""
    if not await system_flags.is_enabled(db, "game_mafia_v1"):
        return
    await _guarded("lobby expiry", mafia.expire_stale_lobbies(db))
    for match_id in await repo.due_match_ids(db):
        await _guarded(f"advance {match_id}", mafia.advance_due_match(db, match_id=match_id))
    for match_id in await ops.pending_event_ids(db):
        await _guarded(f"deliver {match_id}", deliver_for_match(bot, db, match_id))
    for row in await repo.timed_matches(db):
        view = await mafia.current_view(db, match_id=int(row["id"]))
        if view:
            gap = rules.CARD_VOTING_REFRESH_SECONDS if view["phase"] == "voting" else rules.CARD_REFRESH_SECONDS
            await _guarded(f"refresh {row['id']}", publish_phase(bot, db, view, gap=gap))
