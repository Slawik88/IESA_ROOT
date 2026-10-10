"""События участников: бот добавлен, владелец сменился, кто-то вошёл или вышел."""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.types import ChatMemberUpdated

from bot.chat import ranks
from bot.chat.moderation import commit, is_blacklisted

router = Router(name="chat_members")
INSIDE = ("member", "administrator", "creator", "restricted")


@router.my_chat_member()
async def on_bot_membership(event: ChatMemberUpdated, bot: Bot, db) -> None:
    """Бота добавили в группу или повысили — сразу узнаём владельца."""
    if event.chat.type in ("group", "supergroup") and event.new_chat_member.status in ("member", "administrator"):
        await ranks.sync_owner(db, bot, event.chat.id, force=True)


@router.chat_member()
async def on_member_change(event: ChatMemberUpdated, bot: Bot, db) -> None:
    chat_id = event.chat.id
    new, old = event.new_chat_member, event.old_chat_member
    user = new.user
    # Передача прав на группу в Telegram -> новый владелец в боте.
    if new.status == "creator":
        await ranks.set_owner(db, chat_id, user.id)
    elif old.status == "creator":
        await ranks.sync_owner(db, bot, chat_id, force=True)

    joined = new.status in INSIDE and old.status not in INSIDE
    left = old.status in INSIDE and new.status not in INSIDE
    if joined and not user.is_bot:
        # Чёрный список чата: забаненный, зашедший по ссылке, сразу удаляется.
        if not ranks.is_developer(user.id) and await is_blacklisted(db, chat_id, user.id):
            try:
                await bot.ban_chat_member(chat_id, user.id)
            except Exception:
                pass
            return
        await db.execute(
            "INSERT INTO user_chat_stats (user_tg_id, chat_tg_id, is_left) VALUES (?, ?, FALSE) "
            "ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE SET is_left = FALSE",
            (user.id, chat_id))
        await commit(db)
    elif left and not user.is_bot:
        await db.execute(
            "UPDATE user_chat_stats SET is_left = TRUE WHERE chat_tg_id = ? AND user_tg_id = ?", (chat_id, user.id))
        await commit(db)
