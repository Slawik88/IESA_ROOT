"""
filters/feature_flag.py — Feature Flags (per-chat module toggles).

Usage in a handler:
    from filters.feature_flag import feature_enabled

    @router.message(BotCommand("брак", "marry"))
    async def cmd_marry(message: Message, ...):
        if not await feature_enabled(message, "marriages"):
            return
        ...

Available features: website, antispam, marriages, pets, casino, random_events.
"""

import time
from aiogram.types import Message
import logging
_log = logging.getLogger(__name__)

# Anti-spam cooldown for "feature disabled" replies:
# don't repeat the message if the same user triggered it within N seconds.
_disabled_reply_cooldown: dict[tuple[int, int, str], float] = {}
_DISABLED_REPLY_COOLDOWN = 30.0  # seconds


def _feat_key(feature: str) -> str:
    return f"feat_{feature}"


async def feature_enabled(message: Message, feature: str) -> bool:
    """Return True if the feature is enabled for this chat.

    If disabled, sends a throttled warning reply and returns False.
    The caller should simply ``return`` after a False result.
    """
    chat_id = message.chat.id
    if message.chat.type not in ("group", "supergroup"):
        # Always allow in private / channels
        return True

    from database.db import get_chat_settings
    settings = await get_chat_settings(chat_id)

    col = _feat_key(feature)
    if settings is not None:
        # Default: 1 (enabled). Disabled only when explicitly set to 0.
        try:
            val = settings[col]
        except (KeyError, IndexError):
            val = 1
        if val == 0:
            _send_disabled_notice(message, feature)
            return False
    return True


def _send_disabled_notice(message: Message, feature: str):
    """Fire-and-forget throttled reply when a disabled feature is invoked."""
    import asyncio
    uid = message.from_user.id if message.from_user else 0
    chat_id = message.chat.id
    key = (uid, chat_id, feature)
    now = time.monotonic()
    if now - _disabled_reply_cooldown.get(key, 0) < _DISABLED_REPLY_COOLDOWN:
        return
    _disabled_reply_cooldown[key] = now

    async def _reply():
        try:
            await message.reply(
                "⚠️ Эта функция отключена администрацией чата.",
            )
        except Exception as _e:
            _log.debug("%s", _e)
    asyncio.create_task(_reply())
