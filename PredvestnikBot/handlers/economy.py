"""
Команды экономики: валюта Мора.

  бот баланс              — твой баланс в этом чате
  бот баланс @user        — баланс другого пользователя (только если открыт)
"""
import html

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import get_mora, get_user, set_mora_public
from filters.bot_command import BotCommand
from utils.helpers import resolve_target, user_mention

router = Router()


def _mora_text(balance: int, total: int, streak: int, public: int) -> str:
    streak_line = f"\n🔥 Стрик: <b>{streak} дн.</b>" if streak > 0 else ""
    privacy_line = "🔓 Баланс виден другим" if public else "🔒 Баланс скрыт от других"
    return (
        f"💰 <b>Твой баланс</b>\n\n"
        f"Мора: <b>{balance} 🪙</b>\n"
        f"Всего заработано: {total} 🪙"
        f"{streak_line}\n\n"
        f"{privacy_line}"
    )


def _mora_keyboard(uid: int, public: int) -> InlineKeyboardMarkup:
    label = "🔒 Скрыть баланс" if public else "🔓 Показать другим"
    new_val = 0 if public else 1
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=label, callback_data=f"mora_pub:{uid}:{new_val}"),
    ]])


@router.message(BotCommand("баланс", "мора", "mora", "balance"))
async def cmd_balance(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    chat_id = message.chat.id
    arg = (cmd_args or "").strip()

    if arg:
        # Проверяем баланс другого пользователя
        uid, name, _ = await resolve_target(message, arg)
        if uid is None:
            await message.answer(name)  # name содержит сообщение об ошибке
            return

        mora = await get_mora(uid, chat_id)
        if mora and mora["mora_public"]:
            balance = mora["balance"] or 0
            total   = mora["total_earned"] or 0
            user    = await get_user(uid)
            display = html.escape(user["full_name"]) if user else html.escape(name)
            await message.answer(
                f"💰 <b>Баланс</b> {user_mention(uid, display)}\n\n"
                f"Мора: <b>{balance} 🪙</b>\n"
                f"Всего заработано: {total} 🪙",
                parse_mode="HTML",
            )
        else:
            await message.answer("🔒 Этот пользователь скрыл свой баланс.")
        return

    # Свой баланс
    uid    = message.from_user.id
    mora   = await get_mora(uid, chat_id)
    bal    = mora["balance"]     if mora else 0
    total  = mora["total_earned"] if mora else 0
    streak = mora["streak_days"] if mora else 0
    public = mora["mora_public"] if mora else 0

    await message.answer(
        _mora_text(bal, total, streak, public),
        parse_mode="HTML",
        reply_markup=_mora_keyboard(uid, public),
    )


@router.callback_query(F.data.startswith("mora_pub:"))
async def cb_mora_public(callback: CallbackQuery):
    parts   = callback.data.split(":")
    uid     = int(parts[1])
    new_val = int(parts[2])

    if callback.from_user.id != uid:
        await callback.answer("🚫 Это не твоё меню!", show_alert=True)
        return

    chat_id = callback.message.chat.id
    await set_mora_public(uid, chat_id, new_val)

    mora   = await get_mora(uid, chat_id)
    bal    = mora["balance"]      if mora else 0
    total  = mora["total_earned"] if mora else 0
    streak = mora["streak_days"]  if mora else 0

    try:
        await callback.message.edit_text(
            _mora_text(bal, total, streak, new_val),
            parse_mode="HTML",
            reply_markup=_mora_keyboard(uid, new_val),
        )
    except Exception:
        pass
    await callback.answer("✅ Настройки обновлены!")
