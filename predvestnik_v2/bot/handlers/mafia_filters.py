"""Telegram-side helpers shared by the Mafia handlers, the message gate and the scheduler."""
from __future__ import annotations

import asyncio

from aiogram import Bot, types
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import BaseFilter
from loguru import logger

from core import mafia_command
from core.mafia_copy import ALERT_LIMIT


class MafiaCmd(BaseFilter):
    """Matches «бот мафия», «бот мафия стоп», «/mafia@bot 8» and injects ``mafia_cmd``."""

    async def __call__(self, message: types.Message) -> dict | bool:
        command = mafia_command.parse(message.text)
        return {"mafia_cmd": command} if command else False


def topic_of(message: types.Message | None) -> int | None:
    """Forum-topic id of a message.

    ``message_thread_id`` is also filled for plain reply chains in ordinary supergroups; using
    it raw would put a lobby opened by a reply into a phantom "topic" no later message matches.
    """
    if message is None or not getattr(message, "is_topic_message", False):
        return None
    return getattr(message, "message_thread_id", None)


def clip_alert(text: str) -> str:
    """Telegram rejects callback alerts longer than 200 characters."""
    return text if len(text) <= ALERT_LIMIT else text[: ALERT_LIMIT - 1] + "…"


async def answer(query: types.CallbackQuery, text: str = "", *, alert: bool = False, url: str | None = None) -> None:
    """Always stop the button spinner; an expired query must never crash a handler."""
    try:
        await query.answer(clip_alert(text) if text else None, show_alert=alert, url=url)
    except TelegramBadRequest as exc:
        logger.debug(f"Mafia callback answer skipped: {exc}")


async def is_chat_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
    except TelegramAPIError:
        return False
    return member.status in {"administrator", "creator"}


async def bot_can_moderate(bot: Bot, chat_id: int) -> bool:
    try:
        me = await bot.me()
        member = await bot.get_chat_member(chat_id, me.id)
    except TelegramAPIError:
        return False
    return member.status in {"administrator", "creator"} and bool(getattr(member, "can_delete_messages", False))


async def dm_reachable(bot: Bot, user_id: int) -> bool:
    """True when the bot may message the user (they pressed Start and have not blocked it)."""
    try:
        await bot.send_chat_action(int(user_id), "typing")
        return True
    except (TelegramForbiddenError, TelegramBadRequest):
        return False
    except TelegramAPIError as exc:
        logger.warning(f"Mafia DM probe inconclusive for {user_id}: {exc}")
        return True  # a flood/network hiccup must not look like a closed DM


async def unreachable_players(bot: Bot, user_ids: list[int]) -> list[int]:
    results = await asyncio.gather(*(dm_reachable(bot, uid) for uid in user_ids))
    return [uid for uid, ok in zip(user_ids, results) if not ok]


async def cannot_write(bot: Bot, chat_id: int, players: list[dict]) -> list[str]:
    """Fresh Telegram membership check; cached chat statistics are insufficient."""
    async def check(player: dict) -> str | None:
        try:
            member = await bot.get_chat_member(chat_id, int(player["user_id"]))
        except TelegramAPIError:
            return player["display_name"]
        active = member.status in {"member", "administrator", "creator", "restricted"}
        can_write = member.status != "restricted" or bool(getattr(member, "can_send_messages", False))
        return None if active and can_write else player["display_name"]
    return [name for name in await asyncio.gather(*(check(p) for p in players)) if name]


async def bot_username(bot: Bot) -> str | None:
    try:
        return (await bot.me()).username
    except TelegramAPIError:
        return None
