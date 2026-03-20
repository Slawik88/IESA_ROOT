import html
from datetime import datetime, timedelta

from aiogram import Bot, Router
from aiogram.types import ChatPermissions, Message

from config import MAX_WARNS
from database.db import add_warn_in_chat, get_user_stats
from filters.bot_command import BotCommand
from filters.rank_filter import RankFilter
from utils.helpers import parse_time, resolve_target, user_mention
from utils.ranks import rank_level

router = Router()

_bot_id: int | None = None


def _protected(rank: str) -> bool:
    return rank_level(rank) >= rank_level("moderator")


@router.message(BotCommand("варн", "warn", "предупредить", "предупреждение"), RankFilter("moderator"))
async def cmd_warn(message: Message, bot: Bot, cmd_args: str):
    global _bot_id
    uid, name, reason = await resolve_target(message, cmd_args)
    if uid is None:
        await message.answer(name)
        return

    if uid == message.from_user.id:
        await message.answer("❌ Нельзя предупредить самого себя.")
        return
    if _bot_id is None:
        _bot_id = (await bot.get_me()).id
    if uid == _bot_id:
        await message.answer("❌ Нельзя предупредить бота.")
        return

    target_stats = await get_user_stats(uid, message.chat.id)
    if target_stats and _protected(target_stats["rank"]):
        await message.answer("❌ Нельзя предупредить члена администрации.")
        return

    reason = reason or "не указана"
    warns = await add_warn_in_chat(uid, message.chat.id)

    if warns >= MAX_WARNS:
        # Не баним автоматически — уведомляем стафф в ЛС, они решают сами
        chat_title = html.escape(getattr(message.chat, "title", None) or str(message.chat.id))
        notify_text = (
            f"🚨 <b>Лимит предупреждений достигнут!</b>\n\n"
            f"👤 Пользователь: {user_mention(uid, name)}\n"
            f"💬 Чат: {chat_title}\n"
            f"⚠️ Предупреждений: <b>{warns}/{MAX_WARNS}</b>\n"
            f"📝 Последняя причина: {html.escape(reason)}\n\n"
            f"Выдай бан или кик:\n"
            f"<code>бот бан {uid}</code>\n"
            f"<code>бот кик {uid}</code>"
        )
        from utils.helpers import notify_admins
        await notify_admins(bot, notify_text, source_chat_id=message.chat.id)

        await message.answer(
            f"🚨 {user_mention(uid, name)} достиг лимита предупреждений "
            f"(<b>{warns}/{MAX_WARNS}</b>)!\n"
            f"📝 Причина: {reason}\n"
            f"<i>Администрация уведомлена.</i>",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"⚠️ {user_mention(uid, name)} получил предупреждение ({warns}/{MAX_WARNS})\n"
            f"📝 Причина: {reason}",
            parse_mode="HTML",
        )


@router.message(BotCommand("мут", "mute", "замутить", "заглушить"), RankFilter("moderator"))
async def cmd_mute(message: Message, bot: Bot, cmd_args: str):
    uid, name, rest = await resolve_target(message, cmd_args)
    if uid is None:
        await message.answer(
            name + "\nПример: <code>бот мут 10м причина</code>",
            parse_mode="HTML",
        )
        return

    if uid == message.from_user.id:
        await message.answer("❌ Нельзя заглушить самого себя.")
        return

    target_stats = await get_user_stats(uid, message.chat.id)
    if target_stats and _protected(target_stats["rank"]):
        await message.answer("❌ Нельзя заглушить члена администрации.")
        return

    # Парсим время из первого слова rest
    parts = rest.split(maxsplit=1) if rest else []
    if parts and parts[0][:-1].isdigit():
        duration, time_label = parse_time(parts[0])
        reason = parts[1] if len(parts) > 1 else "не указана"
    else:
        duration, time_label = 300, "5 мин."
        reason = rest or "не указана"

    until = datetime.now() + timedelta(seconds=duration)
    try:
        await bot.restrict_chat_member(
            message.chat.id, uid,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        await message.answer(
            f"🔇 {user_mention(uid, name)} заглушен на {time_label}\n"
            f"📝 Причина: {reason}",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Не удалось заглушить: {e}")



