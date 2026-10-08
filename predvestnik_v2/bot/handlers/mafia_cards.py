"""Publishing the one living phase card in the group (edit in place, never duplicate)."""
from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import (TelegramAPIError, TelegramBadRequest, TelegramForbiddenError,
                                TelegramNetworkError, TelegramRetryAfter, TelegramServerError)
from loguru import logger

from bot.handlers.mafia_card_views import phase_keyboard, phase_text
from bot.handlers.mafia_filters import bot_username
from bot.handlers.mafia_views import lobby_keyboard, lobby_text
from core import mafia_v1 as rules
from infrastructure.repositories import mafia_v1 as repo
from infrastructure.repositories import mafia_v1_ops as ops

# The card is gone or can never be edited again: only then is a replacement correct.
_GONE = ("message to edit not found", "message can't be edited", "message_id_invalid", "message identifier is not specified")
_TRANSIENT = (TelegramRetryAfter, TelegramNetworkError, TelegramServerError)


def _keyboard_for(view: dict, username: str | None):
    return None if view["phase"] in ("finished", "cancelled") else phase_keyboard(view, username)


async def _edit(bot: Bot, view: dict, text: str, keyboard) -> str:
    """'ok' | 'gone' (recreate) | 'later' (transient failure: do nothing now)."""
    try:
        await bot.edit_message_text(text, chat_id=view["chat_id"], message_id=view["phase_message_id"],
                                    reply_markup=keyboard, parse_mode="HTML")
        return "ok"
    except TelegramBadRequest as exc:
        message = str(exc).lower()
        if "message is not modified" in message:
            return "ok"
        if any(marker in message for marker in _GONE):
            return "gone"
        logger.warning(f"Mafia card edit rejected: {exc}")
        return "later"
    except _TRANSIENT as exc:
        logger.warning(f"Mafia card edit postponed: {exc}")
        return "later"
    except TelegramForbiddenError as exc:
        logger.warning(f"Mafia card edit forbidden: {exc}")
        return "ok"  # kicked/blocked: nothing can be shown, do not loop forever


async def _send(bot: Bot, db, view: dict, text: str, keyboard) -> bool:
    try:
        sent = await bot.send_message(view["chat_id"], text, reply_markup=keyboard, parse_mode="HTML",
                                      message_thread_id=view.get("topic_id"))
    except _TRANSIENT as exc:
        logger.warning(f"Mafia card send postponed: {exc}")
        return False
    except TelegramAPIError as exc:
        logger.warning(f"Mafia card send failed: {exc}")
        return True  # permanent (kicked/forbidden): stop retrying
    await repo.bind_phase_message(db, match_id=view["match_id"], message_id=int(sent.message_id))
    return True


async def _drop_old(bot: Bot, view: dict) -> None:
    try:
        await bot.delete_message(view["chat_id"], view["phase_message_id"])
    except TelegramAPIError:
        try:
            await bot.edit_message_reply_markup(chat_id=view["chat_id"], message_id=view["phase_message_id"], reply_markup=None)
        except TelegramAPIError as exc:
            logger.debug(f"Mafia old card could not be retired: {exc}")


async def publish_phase(bot: Bot, db, view: dict, *, gap: float = rules.CARD_REFRESH_SECONDS, repost: bool = False) -> bool:
    """Bring the group card to ``view``.  True when done; False asks the caller to retry later.

    ``gap`` paces edits across processes (0 = always).  ``repost`` puts a fresh card at the bottom
    of the chat (voting starts after a chatty discussion) and retires the old one afterwards.
    """
    if not await ops.claim_card_refresh(db, match_id=view["match_id"], gap_seconds=gap):
        return True
    text, keyboard = phase_text(view), _keyboard_for(view, await bot_username(bot))
    if view.get("phase_message_id") and not repost:
        outcome = await _edit(bot, view, text, keyboard)
        if outcome != "gone":
            return outcome == "ok"
    old = view.get("phase_message_id")
    if not await _send(bot, db, view, text, keyboard):
        return False
    if repost and old:
        await _drop_old(bot, {**view, "phase_message_id": old})
    return True


async def post_lobby(bot: Bot, db, view: dict, topic: int | None, *, retire_old: bool = False) -> None:
    """Put the lobby card at the bottom of the chat; ``retire_old`` removes the buried copy."""
    sent = await bot.send_message(view["chat_id"], lobby_text(view), reply_markup=lobby_keyboard(view, await bot_username(bot)),
                                  parse_mode="HTML", message_thread_id=topic)
    old = view.get("lobby_message_id")
    await repo.bind_lobby_message(db, match_id=view["match_id"], message_id=int(sent.message_id))
    if retire_old and old:
        await _drop_old(bot, {**view, "phase_message_id": old})


async def bump_card(bot: Bot, db, view: dict) -> None:
    """The chat scrolled past the game card: bring it back (one fresh card, old one removed)."""
    if view["phase"] == "lobby":
        await post_lobby(bot, db, view, view.get("topic_id"), retire_old=True)
    else:
        await publish_phase(bot, db, view, gap=0, repost=True)
