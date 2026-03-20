import asyncio
import html

from aiogram import Bot, F, Router
from aiogram.types import (
    CallbackQuery,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import (
    ban_user_in_chat, get_banned_in_chat, get_user, get_user_stats,
    remove_warn_in_chat, unban_user_in_chat,
)
from filters.bot_command import BotCommand
from filters.rank_filter import RankFilter
from utils.helpers import resolve_target, user_mention
from utils.ranks import rank_level

router = Router()


def _protected(rank: str) -> bool:
    return rank_level(rank) >= rank_level("moderator")


@router.message(BotCommand("бан", "ban", "забанить"), RankFilter("moderator"))
async def cmd_ban(message: Message, bot: Bot, cmd_args: str):
    uid, name, reason = await resolve_target(message, cmd_args)
    if uid is None:
        await message.answer(name)
        return

    target_stats = await get_user_stats(uid, message.chat.id)
    if target_stats and _protected(target_stats["rank"]):
        await message.answer("❌ Нельзя заблокировать члена администрации.")
        return

    reason = reason or "не указана"
    await ban_user_in_chat(uid, message.chat.id, reason)
    try:
        await bot.ban_chat_member(message.chat.id, uid)
    except Exception as e:
        await message.answer(f"❌ Telegram не дал забанить: {e}")
        return

    await message.answer(
        f"⛔ {user_mention(uid, name)} <b>заблокирован</b>.\n"
        f"📝 Причина: {reason}",
        parse_mode="HTML",
    )


@router.message(BotCommand("кик", "выгнать", "кикнуть", "kick"), RankFilter("moderator"))
async def cmd_kick(message: Message, bot: Bot, cmd_args: str):
    uid, name, reason = await resolve_target(message, cmd_args)
    if uid is None:
        await message.answer(name)
        return

    target_stats = await get_user_stats(uid, message.chat.id)
    if target_stats and _protected(target_stats["rank"]):
        await message.answer("❌ Нельзя выгнать члена администрации.")
        return

    try:
        await bot.ban_chat_member(message.chat.id, uid)
        await bot.unban_chat_member(message.chat.id, uid)
    except Exception as e:
        await message.answer(f"❌ Не удалось выгнать: {e}")
        return

    reason = reason or "не указана"
    await message.answer(
        f"👢 {user_mention(uid, name)} выгнан из чата.\n"
        f"📝 Причина: {reason}",
        parse_mode="HTML",
    )


@router.message(BotCommand("разбан", "снять бан", "unban"), RankFilter("moderator"))
async def cmd_unban(message: Message, bot: Bot, cmd_args: str):
    uid, name, _ = await resolve_target(message, cmd_args)
    if uid is None:
        await message.answer(name)
        return

    await unban_user_in_chat(uid, message.chat.id)
    try:
        await bot.unban_chat_member(message.chat.id, uid, only_if_banned=True)
    except Exception as e:
        await message.answer(f"❌ Telegram не дал разбанить: {e}")
        return

    await message.answer(
        f"✅ {user_mention(uid, name)} разблокирован.",
        parse_mode="HTML",
    )


@router.message(BotCommand("размут", "снять мут", "unmute"), RankFilter("moderator"))
async def cmd_unmute(message: Message, bot: Bot, cmd_args: str):
    uid, name, _ = await resolve_target(message, cmd_args)
    if uid is None:
        await message.answer(name)
        return

    try:
        await bot.restrict_chat_member(
            message.chat.id, uid,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
            ),
        )
        await message.answer(
            f"🔊 С {user_mention(uid, name)} снят мут.",
            parse_mode="HTML",
        )
    except Exception as e:
        await message.answer(f"❌ Не удалось снять мут: {e}")


@router.message(BotCommand("снять варн", "снятьварн", "разварн", "unwarn"), RankFilter("moderator"))
async def cmd_unwarn(message: Message, cmd_args: str):
    uid, name, _ = await resolve_target(message, cmd_args)
    if uid is None:
        await message.answer(name)
        return

    warns = await remove_warn_in_chat(uid, message.chat.id)
    from config import MAX_WARNS
    await message.answer(
        f"✅ С {user_mention(uid, name)} снято одно предупреждение. Осталось: {warns}/{MAX_WARNS}",
        parse_mode="HTML",
    )


@router.message(BotCommand("закрепить", "пин", "pin"), RankFilter("moderator"))
async def cmd_pin(message: Message, bot: Bot, cmd_args: str):
    if not message.reply_to_message:
        await message.answer(
            "❌ Ответь на сообщение, которое нужно закрепить.\n"
            "ℹ️ Нажми «Ответить» на нужное сообщение и напиши <code>бот пин</code>",
            parse_mode="HTML",
        )
        return
    try:
        await bot.pin_chat_message(
            message.chat.id,
            message.reply_to_message.message_id,
            disable_notification=False,
        )
        await message.answer("📌 Сообщение закреплено.")
    except Exception as e:
        await message.answer(f"❌ Не удалось закрепить: {e}")


@router.message(BotCommand("открепить", "анпин", "unpin"), RankFilter("moderator"))
async def cmd_unpin(message: Message, bot: Bot, cmd_args: str):
    try:
        if message.reply_to_message:
            await bot.unpin_chat_message(message.chat.id, message.reply_to_message.message_id)
        else:
            await bot.unpin_chat_message(message.chat.id)
        await message.answer("📌 Сообщение откреплено.")
    except Exception as e:
        await message.answer(f"❌ Не удалось открепить: {e}")


@router.message(BotCommand("очистить", "purge", "удалить"), RankFilter("moderator"))
async def cmd_purge(message: Message, bot: Bot, cmd_args: str):
    if message.reply_to_message:
        start_id = message.reply_to_message.message_id
        end_id = message.message_id
        ids_to_delete = list(range(start_id, end_id + 1))
    elif cmd_args and cmd_args.isdigit():
        from config import PURGE_MAX
        n = min(int(cmd_args), PURGE_MAX)
        end_id = message.message_id
        ids_to_delete = list(range(end_id - n, end_id + 1))
    else:
        await message.answer(
            "❌ Ответь на сообщение (удалится всё от него до команды), "
            "или укажи количество: <code>бот очистить 10</code>",
            parse_mode="HTML",
        )
        return

    chat_id = message.chat.id
    # Удаляем чанками по 100, считаем поштучно при ошибке батча
    for i in range(0, len(ids_to_delete), 100):
        chunk = ids_to_delete[i:i + 100]
        try:
            await bot.delete_messages(chat_id, chunk)
            # batch API не сообщает сколько реально удалено —
            # пробуем поштучно чтобы точно посчитать
        except Exception:
            pass
        # Поштучный подсчёт: пробуем удалить каждое, считаем успехи
        # Но batch уже удалил что мог — пересчитывать нельзя.
        # Вместо этого просто прибавляем размер чанка (batch удалил что мог)

    # Telegram batch API не возвращает точное кол-во удалённых.
    # Сообщаем диапазон, а не точное число.
    total = len(ids_to_delete)
    note = await message.answer(
        f"🗑 Очистка завершена — обработано {total} ID."
    )
    await asyncio.sleep(3)
    try:
        await note.delete()
    except Exception:
        pass


@router.message(BotCommand("предупреждения", "варны", "warns"), RankFilter("moderator"))
async def cmd_warns(message: Message, cmd_args: str):
    uid, name, _ = await resolve_target(message, cmd_args)
    if uid is None:
        uid = message.from_user.id
        name = message.from_user.full_name

    stats = await get_user_stats(uid, message.chat.id)
    warns = stats["warns"] if stats else 0
    from config import MAX_WARNS
    kb = None
    if warns > 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➖ Снять варн", callback_data=f"uw:{uid}"),
        ]])
    await message.answer(
        f"⚠️ Предупреждения {user_mention(uid, name)}: <b>{warns}/{MAX_WARNS}</b>",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.message(BotCommand("баны", "банлист", "bans"), RankFilter("moderator"))
async def cmd_bans(message: Message, cmd_args: str):
    banned = await get_banned_in_chat(message.chat.id)
    if not banned:
        await message.answer("📋 В этом чате нет заблокированных пользователей.")
        return

    lines = [f"⛔ <b>Заблокированные ({len(banned)}):</b>\n"]
    buttons: list[list[InlineKeyboardButton]] = []
    for u in banned:
        reason = u["ban_reason"] or "не указана"
        lines.append(
            f"  • {user_mention(u['user_id'], html.escape(u['full_name']))} — {html.escape(reason)}"
        )
        buttons.append([InlineKeyboardButton(
            text=f"🔓 Разбан {u['full_name'][:20]}",
            callback_data=f"ub:{u['user_id']}",
        )])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("ub:"))
async def cb_unban(callback: CallbackQuery, bot: Bot):
    caller_stats = await get_user_stats(callback.from_user.id, callback.message.chat.id)
    caller_rank = caller_stats["rank"] if caller_stats else "user"
    if rank_level(caller_rank) < rank_level("moderator"):
        await callback.answer("❌ Недостаточно прав.", show_alert=True)
        return

    uid = int(callback.data.split(":")[1])
    await unban_user_in_chat(uid, callback.message.chat.id)
    user = await get_user(uid)
    name = user["full_name"] if user else str(uid)

    try:
        await bot.unban_chat_member(callback.message.chat.id, uid, only_if_banned=True)
    except Exception:
        pass

    await callback.answer(f"✅ {name} разбанен!", show_alert=True)

    # Обновить список
    banned = await get_banned_in_chat(callback.message.chat.id)
    if not banned:
        try:
            await callback.message.edit_text("📋 В этом чате нет заблокированных пользователей.")
        except Exception:
            pass
        return

    lines = [f"⛔ <b>Заблокированные ({len(banned)}):</b>\n"]
    buttons2: list[list[InlineKeyboardButton]] = []
    for u in banned:
        reason = u["ban_reason"] or "не указана"
        lines.append(f"  • {user_mention(u['user_id'], html.escape(u['full_name']))} — {html.escape(reason)}")
        buttons2.append([InlineKeyboardButton(
            text=f"🔓 Разбан {u['full_name'][:20]}",
            callback_data=f"ub:{u['user_id']}",
        )])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons2) if buttons2 else None
    try:
        await callback.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    except Exception:
        pass


@router.callback_query(F.data.startswith("uw:"))
async def cb_unwarn(callback: CallbackQuery):
    caller_stats = await get_user_stats(callback.from_user.id, callback.message.chat.id)
    caller_rank = caller_stats["rank"] if caller_stats else "user"
    if rank_level(caller_rank) < rank_level("moderator"):
        await callback.answer("❌ Недостаточно прав.", show_alert=True)
        return

    uid = int(callback.data.split(":")[1])
    warns = await remove_warn_in_chat(uid, callback.message.chat.id)
    user = await get_user(uid)
    name = user["full_name"] if user else str(uid)
    from config import MAX_WARNS

    kb = None
    if warns > 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➖ Снять варн", callback_data=f"uw:{uid}"),
        ]])
    try:
        await callback.message.edit_text(
            f"⚠️ Предупреждения {user_mention(uid, name)}: <b>{warns}/{MAX_WARNS}</b>",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        pass
    await callback.answer(f"✅ Варн снят. Осталось: {warns}/{MAX_WARNS}", show_alert=True)


