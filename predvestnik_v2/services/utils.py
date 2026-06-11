# services/utils.py
# Re-exports all pure formatting helpers from services/formatting.py.
# Keeps resolve_target here because it is Telegram-specific (works with message objects).
import aiosqlite
from aiogram import types

from aiogram import types as _types

from services.formatting import (  # noqa: F401
    format_currency,
    format_number,
    safe_html,
    format_progress_bar,
    truncate_text,
    format_seconds_to_time,
    parse_dt,
)


async def check_callback_owner(
    query: _types.CallbackQuery, owner_user_id: int
) -> bool:
    """
    Return True if the query is from the expected user; answer with error otherwise.
    If owner_user_id == 0 (legacy button without user_id), allows anyone (backwards compat).
    """
    if owner_user_id == 0:
        return True  # no restriction on old-style buttons
    if query.from_user.id != owner_user_id:
        await query.answer("❌ Это не ваше меню.", show_alert=True)
        return False
    return True


async def resolve_display_name(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    fallback: str,
) -> str:
    """Return the user's local nickname if set, otherwise `fallback` (first_name/username).
    Always pass through safe_html so callers can embed the result in HTML directly.
    Prefixes with 👑 if the user has an active VIP subscription (Implementation Block 3.2)."""
    from infrastructure.repositories.users import get_nickname
    from services.vip import is_vip_active
    from services.profile_render import format_display_name
    nick = await get_nickname(db, user_id, chat_id)
    name = safe_html(nick if nick else fallback)
    return format_display_name(name, await is_vip_active(db, user_id))


async def resolve_target(message: types.Message, db: aiosqlite.Connection, args: str = None):
    """
    Универсальный определитель цели.
    Возвращает: (target_id, target_name, rest_of_text).
    Корректно работает и со слэш-командами, и с TextCmd ("бот варн @user причина").
    """
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        return target.id, target.first_name, args

    if message.entities:
        for entity in message.entities:
            if entity.type == "text_mention":
                return entity.user.id, entity.user.first_name, args

    if not args:
        return None, None, args

    parts = args.split()
    first = parts[0]

    if first.isdigit():
        target_id = int(first)
        async with db.execute(
            "SELECT user_tg_username FROM users WHERE user_tg_id = ?", (target_id,)
        ) as cursor:
            row = await cursor.fetchone()
            name = row[0] if row and row[0] else f"ID {target_id}"
        rest = " ".join(parts[1:])
        return target_id, name, rest

    if first.startswith("@") and len(first) > 1:
        username = first[1:].lower()
        async with db.execute(
            "SELECT user_tg_id, user_tg_username FROM users WHERE LOWER(user_tg_username) = ?",
            (username,),
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            rest = " ".join(parts[1:])
            return row[0], row[1], rest
        return None, None, "error_user_not_found"

    return None, None, args
