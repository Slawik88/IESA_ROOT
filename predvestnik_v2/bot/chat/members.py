"""События участников: бот добавлен, владелец сменился, кто-то вошёл или вышел."""
from __future__ import annotations

from aiogram import Bot, Router
from aiogram.types import ChatMemberUpdated

from bot.chat import ranks
from bot.chat.moderation import commit, is_blacklisted
from services import member_tags

router = Router(name="chat_members")
INSIDE = ("member", "administrator", "creator", "restricted")


def _inside(member) -> bool:
    """В чате ли человек. Замученный (restricted) может быть уже вышедшим: у него is_member = False."""
    return member.status in INSIDE and (member.status != "restricted" or getattr(member, "is_member", True))


@router.my_chat_member()
async def on_bot_membership(event: ChatMemberUpdated, bot: Bot, db) -> None:
    """Что случилось с самим ботом. Группа: добавили (сразу узнаём владельца), повысили или понизили, удалили.
    Личка: игрок заблокировал бота или вернулся. Это нужно рассылкам и вкладке «Состояние» админки."""
    new = event.new_chat_member
    if event.chat.type == "private":
        await db.execute(
            "UPDATE users SET dm_blocked_at = CASE WHEN ? THEN COALESCE(dm_blocked_at, NOW()) ELSE NULL END "
            "WHERE user_tg_id = ?", (new.status == "kicked", event.chat.id))
        await commit(db)
        return
    if event.chat.type not in ("group", "supergroup"):
        return
    if new.status in ("left", "kicked"):
        await db.execute(
            "INSERT INTO chat_settings (chat_id, chat_title, bot_left_at, bot_is_admin, bot_can_moderate) "
            "VALUES (?, ?, NOW(), FALSE, FALSE) ON CONFLICT (chat_id) DO UPDATE SET "
            "bot_left_at = COALESCE(chat_settings.bot_left_at, NOW()), bot_is_admin = FALSE, bot_can_moderate = FALSE",
            (event.chat.id, event.chat.title))
        await commit(db)
    elif new.status in ("member", "administrator"):
        is_admin = new.status == "administrator"
        can_moderate = is_admin and bool(getattr(new, "can_delete_messages", False)) and bool(getattr(new, "can_restrict_members", False))
        await db.execute(
            "INSERT INTO chat_settings (chat_id, chat_title, bot_left_at, bot_is_admin, bot_can_moderate) "
            "VALUES (?, ?, NULL, ?, ?) ON CONFLICT (chat_id) DO UPDATE SET bot_left_at = NULL, "
            "bot_is_admin = EXCLUDED.bot_is_admin, bot_can_moderate = EXCLUDED.bot_can_moderate, "
            "chat_title = COALESCE(EXCLUDED.chat_title, chat_settings.chat_title)",
            (event.chat.id, event.chat.title, is_admin, can_moderate))
        await commit(db)
        await ranks.sync_owner(db, bot, event.chat.id, force=True)
    try:   # приветствие с чек-листом, обновление при выдаче прав, запись об уходе (воронка подключения)
        from bot.chat import onboarding
        await onboarding.on_bot_change(event, bot, db)
    except Exception as exc:   # noqa: BLE001 - подключение чата не должно ломать учёт прав бота
        from loguru import logger
        logger.warning(f"onboarding failed for {event.chat.id}: {exc}")


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

    joined = _inside(new) and not _inside(old)
    left = _inside(old) and not _inside(new)
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
            "ON CONFLICT (user_tg_id, chat_tg_id) DO UPDATE SET is_left = FALSE, "
            "rejoined_at = CASE WHEN COALESCE(user_chat_stats.is_left, FALSE) THEN NOW() "
            "ELSE user_chat_stats.rejoined_at END",
            (user.id, chat_id))
        await member_tags.observe(db, chat_id, user.id, member_tags.of_member(new))   # вошёл или ему сменили тег/права
        await commit(db)
    elif _inside(new) and not user.is_bot:
        await member_tags.observe(db, chat_id, user.id, member_tags.of_member(new))   # остался в чате, но сменился тег или звание
        await commit(db)
    elif left and not user.is_bot:
        await db.execute(
            "UPDATE user_chat_stats SET is_left = TRUE WHERE chat_tg_id = ? AND user_tg_id = ?", (chat_id, user.id))
        await commit(db)
