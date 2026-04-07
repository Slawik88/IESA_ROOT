"""
middlewares/callback_isolation.py — Block economy callback queries in isolated chats.

Injects `is_isolated_chat` into handler data for every callback query.
When the callback originates from an admin-group or test-chat,
silently answers the callback and prevents handler execution
(except for admin/moderation callbacks that must work in those chats).
"""
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery

from database.db import get_admin_group_ids, is_test_chat

# Callback prefixes that should work in isolated chats (admin/mod/non-economy).
_ADMIN_PREFIXES = (
    "su:f:",          # owner: setuser field hint
    "rag:",           # owner: remove admin group
    "rmal:",          # owner: remove chat-admin link
    "ct:del:",        # owner: remove channel type
    "rl:holders:",    # owner: show role holders
    "ub:",            # moderator: unban
    "uw:",            # moderator: unwarn
    "dfl:",           # extras: default language
    "ban_u:",         # extras: ban user
    "dn:",            # notes: delete note
    "lk:",            # auto_mod: locks toggle
    "dbw:",           # auto_mod: delete blacklist word
    "blt:",           # auto_mod: blacklist toggle
    "h:",             # user: help pages
    "top:",           # user: top pages
    "pn:",            # user: pagination
    "dr:",            # dm_roles: DM role onboarding
    "anon_forward:",  # economy: forward anonymous message to main chat
)


class CallbackIsolationMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[CallbackQuery, Dict[str, Any]], Awaitable[Any]],
        event: CallbackQuery,
        data: Dict[str, Any],
    ) -> Any:
        chat = event.message.chat if event.message else None
        is_isolated = False

        if chat and chat.type in ("group", "supergroup"):
            is_isolated = (
                chat.id in get_admin_group_ids() or is_test_chat(chat.id)
            )

        data["is_isolated_chat"] = is_isolated

        if is_isolated:
            cb_data = event.data or ""
            # Allow admin/moderation callbacks through
            if not cb_data.startswith(_ADMIN_PREFIXES):
                try:
                    await event.answer(
                        "\u26d4 Экономика отключена в этом чате.", show_alert=False,
                    )
                except Exception:
                    pass
                return  # block handler

        return await handler(event, data)
