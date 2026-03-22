"""
Экспедиции питомцев.

Команды:
  бот экспедиция      — отправить питомца в экспедицию (выбор времени)
  бот экспедиция статус — посмотреть статус текущей экспедиции
"""

import html
from datetime import datetime, timedelta, timezone

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import EXPEDITION_OPTIONS
from database.db import (
    add_mora,
    deduct_mora,
    get_active_expedition,
    get_mora,
    get_pet,
    start_expedition,
)
from filters.bot_command import BotCommand
from utils.helpers import user_mention

router = Router()


def _time_left(started_at_iso: str, duration_h: int) -> str:
    started = datetime.fromisoformat(started_at_iso)
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    end = started.replace(tzinfo=timezone.utc) + timedelta(hours=duration_h)
    diff = end - now
    if diff.total_seconds() <= 0:
        return "завершена!"
    hours, rem = divmod(int(diff.total_seconds()), 3600)
    minutes = rem // 60
    if hours > 0:
        return f"{hours}ч {minutes}мин"
    return f"{minutes}мин"


@router.message(BotCommand("экспедиция", "поход", "expedition"))
async def cmd_expedition(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Экспедиции доступны только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    arg = (cmd_args or "").strip().lower()

    pet = await get_pet(uid, chat_id)
    if not pet:
        await message.answer(
            "❌ У тебя нет питомца.\n"
            "Сначала заведи: <code>бот завести питомца</code>",
            parse_mode="HTML",
        )
        return

    # Проверяем, не в экспедиции ли уже
    active = await get_active_expedition(uid, chat_id)
    if active:
        left = _time_left(active["started_at"], active["duration_h"])
        pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet["pet_type"], "🐾")
        pet_name = html.escape(pet["name"]) if pet.get("name") else "безымянный"
        await message.answer(
            f"🗺 <b>Питомец в экспедиции</b>\n\n"
            f"{pet_emoji} <b>{pet_name}</b> сейчас в походе.\n"
            f"⏳ Осталось: <b>{left}</b>\n"
            f"💰 Награда: <b>{active['reward_min']}–{active['reward_max']} 🪙</b>",
            parse_mode="HTML",
        )
        return

    # Показываем меню выбора
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0

    rows = []
    for key, opt in EXPEDITION_OPTIONS.items():
        cost_text = f"{opt['cost']} 🪙" if opt["cost"] > 0 else "бесплатно"
        rows.append([InlineKeyboardButton(
            text=f"🗺 {opt['label']} — {cost_text} (награда {opt['reward_min']}–{opt['reward_max']})",
            callback_data=f"exped:{uid}:{key}",
        )])

    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet["pet_type"], "🐾")
    pet_name = html.escape(pet["name"]) if pet.get("name") else "безымянный"
    await message.answer(
        f"🗺 <b>Экспедиция</b>\n\n"
        f"Отправь {pet_emoji} <b>{pet_name}</b> в поход за Морой!\n"
        f"Твой баланс: <b>{bal} 🪙</b>\n\n"
        f"Выбери длительность:",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(lambda c: c.data and c.data.startswith("exped:"))
async def cb_expedition_start(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    key = parts[2]

    if callback.from_user.id != owner:
        await callback.answer("❌ Это не твоя кнопка!", show_alert=True)
        return

    chat_id = callback.message.chat.id
    uid = owner

    opt = EXPEDITION_OPTIONS.get(key)
    if not opt:
        await callback.answer("❌ Неизвестный вариант.", show_alert=True)
        return

    pet = await get_pet(uid, chat_id)
    if not pet:
        await callback.answer("❌ У тебя нет питомца!", show_alert=True)
        return

    active = await get_active_expedition(uid, chat_id)
    if active:
        await callback.answer("❌ Питомец уже в экспедиции!", show_alert=True)
        return

    cost = opt["cost"]
    if cost > 0:
        ok, new_bal = await deduct_mora(uid, chat_id, cost)
        if not ok:
            mora = await get_mora(uid, chat_id)
            bal = mora["balance"] if mora else 0
            await callback.answer(
                f"❌ Недостаточно Моры! ({bal} / {cost})", show_alert=True
            )
            return

    ok = await start_expedition(
        uid, chat_id, opt["hours"], opt["reward_min"], opt["reward_max"]
    )
    if not ok:
        if cost > 0:
            await add_mora(uid, chat_id, cost)
        await callback.answer("❌ Не удалось начать экспедицию.", show_alert=True)
        return

    pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet["pet_type"], "🐾")
    pet_name = html.escape(pet["name"]) if pet.get("name") else "безымянный"
    cost_text = f"Списано <b>{cost} 🪙</b>" if cost > 0 else "Бесплатно"

    try:
        await callback.message.edit_text(
            f"🗺 <b>Экспедиция начата!</b>\n\n"
            f"{pet_emoji} <b>{pet_name}</b> отправился в поход на <b>{opt['label']}</b>.\n"
            f"💰 {cost_text}\n"
            f"🎁 Ожидаемая награда: <b>{opt['reward_min']}–{opt['reward_max']} 🪙</b>\n\n"
            f"<i>Питомец вернётся автоматически. Уведомление придёт в чат.</i>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer(f"🗺 Экспедиция на {opt['label']} начата!")
