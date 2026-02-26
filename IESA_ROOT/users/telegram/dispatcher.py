"""Update dispatcher — routes incoming Telegram updates to handlers."""
from __future__ import annotations

import logging
from typing import Any

from asgiref.sync import sync_to_async

from .client import send_message_async
from .handlers import (
    handle_echo,
    handle_help,
    handle_id,
    handle_link,
    handle_start,
    handle_status,
    handle_unlink,
)

logger = logging.getLogger(__name__)

# Command → handler mapping
COMMANDS: dict[str, Any] = {
    "/start":  handle_start,
    "/help":   handle_help,
    "/link":   handle_link,
    "/id":     handle_id,
    "/status": handle_status,
    "/unlink": handle_unlink,
}


async def _get_user_by_chat_id(chat_id: int):
    """Return Django User with telegram_chat_id == chat_id, or None."""
    def _query():
        from users.models import User
        return User.objects.filter(telegram_chat_id=chat_id).first()
    return await sync_to_async(_query)()


async def process_incoming_update(update: dict[str, Any]) -> bool:
    """
    Process one incoming Telegram update.

    Supports: message, edited_message.
    Routes commands to registered handlers; everything else → echo.
    """
    message  = update.get("message") or update.get("edited_message") or {}
    chat     = message.get("chat") or {}
    chat_id  = chat.get("id")
    text     = (message.get("text") or "").strip()

    if not chat_id:
        return False

    # Resolve linked account (lazy — only used if handler needs it)
    user_db = await _get_user_by_chat_id(chat_id)

    # Match command (may have @botname suffix)
    handler = None
    for cmd, fn in COMMANDS.items():
        if text.lower().startswith(cmd):
            handler = fn
            break

    if handler is None:
        if not text:
            return False
        handler = handle_echo

    try:
        reply = await handler(chat_id, text, user_db)
    except Exception as exc:
        logger.exception("Handler %s raised: %s", handler.__name__, exc)
        reply = "⚠️ Внутренняя ошибка. Попробуй позже."

    if reply:
        return await send_message_async(reply, chat_id=chat_id)
    return False
