"""
Система питомцев.

Разблокируется для пары в браке:
  • брак существует >= PET_MIN_MARRIAGE_DAYS дней (или заблаговременно за Мору)

Команды:
  бот питомец              — посмотреть питомца (или условия для получения)
  бот завести питомца      — выбрать и завести питомца (котёнок / щенок)
  бот назвать питомца <имя> — дать питомцу имя (стоит 40 Моры)
"""

import html
from datetime import datetime, timezone

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from config import PET_MIN_MARRIAGE_DAYS, PET_MORA_SKIP_PRICE, PET_RENAME_PRICE
from database.db import (
    adopt_pet,
    add_mora,
    deduct_mora,
    get_marriage,
    get_mora,
    get_pet,
    get_user,
    rename_pet,
)
from filters.bot_command import BotCommand
from utils.helpers import format_duration, user_mention

router = Router()

_PET_EMOJI = {"cat": "🐱", "dog": "🐶"}
_PET_NAME  = {"cat": "Котёнок", "dog": "Щенок"}


def _marriage_age_days(married_at_iso: str) -> int:
    try:
        dt = datetime.fromisoformat(married_at_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return 0


async def _check_unlock(user_id: int, chat_id: int) -> tuple[bool, str]:
    """
    Проверяет, может ли пользователь завести питомца бесплатно.
    Возвращает (can_adopt: bool, reason: str).
    """
    marriage = await get_marriage(user_id, chat_id)
    if not marriage:
        return False, "💍 Нужно быть в браке."

    age = _marriage_age_days(marriage["married_at"])
    if age < PET_MIN_MARRIAGE_DAYS:
        left = PET_MIN_MARRIAGE_DAYS - age
        return False, (
            f"⏳ Брак слишком молодой.\n"
            f"Нужно ещё <b>{left} дн.</b> (требуется {PET_MIN_MARRIAGE_DAYS} дн.)."
        )

    return True, ""


# ─── бот питомец ──────────────────────────────────────────────────────────────

@router.message(BotCommand("питомец", "пет", "pet"))
async def cmd_pet(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Питомцы доступны только в группах.")
        return

    uid     = message.from_user.id
    chat_id = message.chat.id
    pet     = await get_pet(uid, chat_id)

    if pet:
        await _show_pet(message, pet, uid)
        return

    # Питомца нет — показываем статус разблокировки
    can, reason = await _check_unlock(uid, chat_id)
    if can:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🐱 Котёнок", callback_data=f"pet_adopt:{uid}:cat"),
            InlineKeyboardButton(text="🐶 Щенок",   callback_data=f"pet_adopt:{uid}:dog"),
        ]])
        await message.answer(
            "🎉 <b>Питомец разблокирован!</b>\n\n"
            "Ваша пара выполнила все условия. Выбери питомца:",
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        # Брак есть но слишком молодой — предлагаем пропустить за Мору
        marriage = await get_marriage(uid, chat_id)
        age = _marriage_age_days(marriage["married_at"]) if marriage else 0
        left = max(0, PET_MIN_MARRIAGE_DAYS - age)
        age_bar = "█" * min(10, age) + "░" * max(0, 10 - age)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=f"🐾 Взять сейчас за {PET_MORA_SKIP_PRICE} 🪙",
            callback_data=f"pet_skip:{uid}",
        )]])
        await message.answer(
            f"🐾 <b>Питомец</b>\n\n"
            f"📋 <b>Условие:</b>\n"
            f"  💍 Возраст брака: <b>{age}</b> / {PET_MIN_MARRIAGE_DAYS} дн.  [{age_bar}]\n\n"
            f"Осталось: <b>{left} дн.</b> до автоматической разблокировки.\n"
            f"Или заплатите <b>{PET_MORA_SKIP_PRICE} 🪙</b> чтобы взять питомца сейчас:",
            parse_mode="HTML",
            reply_markup=kb,
        )


async def _show_pet(message: Message, pet: dict, uid: int):
    ptype   = pet["pet_type"]
    emoji   = _PET_EMOJI.get(ptype, "🐾")
    kind    = _PET_NAME.get(ptype, "Питомец")
    name    = html.escape(pet["name"]) if pet.get("name") else f"<i>без имени</i>"
    age     = format_duration(pet["adopted_at"])

    await message.answer(
        f"{emoji} <b>Питомец: {name}</b>\n\n"
        f"🏷 Вид: {kind}\n"
        f"🎂 Возраст: <b>{age}</b>\n\n"
        f"Переименовать: <code>бот назвать питомца Мурзик</code>",
        parse_mode="HTML",
    )


# ─── бот завести питомца ──────────────────────────────────────────────────────

@router.message(BotCommand("завести питомца", "adopt pet", "взять питомца"))
async def cmd_adopt_pet(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Питомцы доступны только в группах.")
        return

    uid     = message.from_user.id
    chat_id = message.chat.id

    existing = await get_pet(uid, chat_id)
    if existing:
        ptype = existing["pet_type"]
        await message.answer(
            f"У тебя уже есть питомец: {_PET_EMOJI.get(ptype, '🐾')} {_PET_NAME.get(ptype, 'Питомец')}.\n"
            "Используй <code>бот питомец</code> чтобы его посмотреть.",
            parse_mode="HTML",
        )
        return

    can, reason = await _check_unlock(uid, chat_id)
    if not can:
        marriage = await get_marriage(uid, chat_id)
        if not marriage:
            await message.answer(
                "❌ Для питомца нужно быть в браке.\n"
                "Найди свою пару: <code>бот брак @username</code>",
                parse_mode="HTML",
            )
            return
        age = _marriage_age_days(marriage["married_at"])
        left = max(0, PET_MIN_MARRIAGE_DAYS - age)
        age_bar = "█" * min(10, age) + "░" * max(0, 10 - age)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text=f"🐾 Взять сейчас за {PET_MORA_SKIP_PRICE} 🪙",
            callback_data=f"pet_skip:{uid}",
        )]])
        await message.answer(
            f"❌ <b>Нельзя завести питомца.</b>\n\n"
            f"📝 Возраст брака: <b>{age}</b> / {PET_MIN_MARRIAGE_DAYS} дн.  [{age_bar}]\n"
            f"Осталось: <b>{left} дн.</b>\n\n"
            f"💎 Или заплати <b>{PET_MORA_SKIP_PRICE} 🪙</b> чтобы взять питомца сейчас:",
            parse_mode="HTML",
            reply_markup=kb,
        )
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🐱 Котёнок", callback_data=f"pet_adopt:{uid}:cat"),
        InlineKeyboardButton(text="🐶 Щенок",   callback_data=f"pet_adopt:{uid}:dog"),
    ]])
    await message.answer("Выбери питомца:", reply_markup=kb)


@router.callback_query(lambda c: c.data and c.data.startswith("pet_adopt:"))
async def cb_pet_adopt(callback: CallbackQuery):
    parts   = callback.data.split(":")
    owner   = int(parts[1])
    ptype   = parts[2]
    uid     = callback.from_user.id
    chat_id = callback.message.chat.id

    if uid != owner:
        await callback.answer("❌ Это не твой выбор.", show_alert=True)
        return

    existing = await get_pet(uid, chat_id)
    if existing:
        await callback.answer("У тебя уже есть питомец!", show_alert=True)
        return

    can, reason = await _check_unlock(uid, chat_id)
    if not can:
        await callback.answer(reason, show_alert=True)
        return

    marriage = await get_marriage(uid, chat_id)
    partner_id = marriage["partner_id"]

    await adopt_pet(uid, partner_id, chat_id, ptype)

    emoji = _PET_EMOJI.get(ptype, "🐾")
    kind  = _PET_NAME.get(ptype, "Питомец")

    partner = await get_user(partner_id)
    partner_name = html.escape(partner["full_name"]) if partner else str(partner_id)

    try:
        await callback.message.edit_text(
            f"{emoji} <b>Поздравляем!</b>\n\n"
            f"Вы с {user_mention(partner_id, partner_name)} завели <b>{kind.lower()}а</b>! 🎉\n\n"
            f"Дайте ему имя: <code>бот назвать питомца Мурзик</code>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer(f"{emoji} Питомец заведён!")


@router.callback_query(lambda c: c.data and c.data.startswith("pet_skip:"))
async def cb_pet_skip(callback: CallbackQuery):
    """Купить питомца за Мору, пропустив ожидание возраста брака."""
    owner = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    chat_id = callback.message.chat.id

    if uid != owner:
        await callback.answer("❌ Это не твоя кнопка!", show_alert=True)
        return

    existing = await get_pet(uid, chat_id)
    if existing:
        await callback.answer("У тебя уже есть питомец!", show_alert=True)
        return

    marriage = await get_marriage(uid, chat_id)
    if not marriage:
        await callback.answer("❌ Нужно быть в браке!", show_alert=True)
        return

    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    if bal < PET_MORA_SKIP_PRICE:
        await callback.answer(
            f"❌ Недостаточно Моры: {bal} / {PET_MORA_SKIP_PRICE} 🪙",
            show_alert=True,
        )
        return

    ok, new_bal = await deduct_mora(uid, chat_id, PET_MORA_SKIP_PRICE)
    if not ok:
        await callback.answer("❌ Не удалось списать Мору.", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🐱 Котёнок", callback_data=f"pet_adopt:{uid}:cat"),
        InlineKeyboardButton(text="🐶 Щенок",   callback_data=f"pet_adopt:{uid}:dog"),
    ]])
    try:
        await callback.message.edit_text(
            f"✅ <b>Оплачено!</b> Потрачено <b>{PET_MORA_SKIP_PRICE} 🪙</b>\n"
            f"Баланс: <b>{new_bal} 🪙</b>\n\n"
            f"Теперь выбери питомца:",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception:
        pass
    await callback.answer("✅ Мора списана, выбирай питомца!")


# ─── бот назвать питомца ──────────────────────────────────────────────────────

@router.message(BotCommand("назвать питомца", "питомец имя", "pet name"))
async def cmd_rename_pet(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Питомцы доступны только в группах.")
        return

    name = (cmd_args or "").strip()
    if not name:
        await message.answer(
            f"❌ Укажи имя.\nПример: <code>бот назвать питомца Мурзик</code>\n"
            f"<i>Стоимость: {PET_RENAME_PRICE} 🪙</i>",
            parse_mode="HTML",
        )
        return

    if len(name) > 32:
        await message.answer("❌ Имя слишком длинное (макс. 32 символа).")
        return

    uid     = message.from_user.id
    chat_id = message.chat.id

    # Проверяем доступность питомца
    pet = await get_pet(uid, chat_id)
    if not pet:
        await message.answer(
            "❌ Питомца нет. Сначала заведи его: <code>бот завести питомца</code>",
            parse_mode="HTML",
        )
        return

    # Проверяем и списываем Мору за переименование
    mora = await get_mora(uid, chat_id)
    bal  = mora["balance"] if mora else 0
    if bal < PET_RENAME_PRICE:
        await message.answer(
            f"❌ Для переименования питомца нужно <b>{PET_RENAME_PRICE} 🪙</b>.\n"
            f"У тебя: <b>{bal} 🪙</b>.",
            parse_mode="HTML",
        )
        return

    ok, new_bal = await deduct_mora(uid, chat_id, PET_RENAME_PRICE)
    if not ok:
        await message.answer("❌ Не удалось списать Мору. Попробуй ещё раз.")
        return

    found = await rename_pet(uid, chat_id, name)
    if found:
        await message.answer(
            f"✅ Питомец переименован в <b>{html.escape(name)}</b>! (<b>-{PET_RENAME_PRICE} 🪙</b>)\n"
            f"Твой баланс: <b>{new_bal} 🪙</b>",
            parse_mode="HTML",
        )
    else:
        # Маловероятно, но если питомец исчез — вернуть деньги
        await add_mora(uid, chat_id, PET_RENAME_PRICE)
        await message.answer(
            "❌ Питомца нет. Сначала заведи его: <code>бот завести питомца</code>",
            parse_mode="HTML",
        )
