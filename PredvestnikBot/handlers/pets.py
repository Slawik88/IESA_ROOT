"""
Система питомцев.

Разблокируется для пары в браке:
  • брак существует >= PET_MIN_MARRIAGE_DAYS дней
  • сумма репутации обоих партнёров >= PET_MIN_COMBINED_REP

Команды:
  бот питомец              — посмотреть питомца (или условия для получения)
  бот завести питомца      — выбрать и завести питомца (котёнок / щенок)
  бот назвать питомца <имя> — дать питомцу имя
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

from config import PET_MIN_COMBINED_REP, PET_MIN_MARRIAGE_DAYS
from database.db import (
    adopt_pet,
    get_marriage,
    get_pet,
    get_user,
    get_user_stats,
    rename_pet,
)
from filters.bot_command import BotCommand
from utils.helpers import user_mention

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
    Проверяет, может ли пользователь завести питомца.
    Возвращает (can_adopt: bool, reason: str).
    """
    marriage = await get_marriage(user_id, chat_id)
    if not marriage:
        return False, f"💍 Нужно быть в браке ({PET_MIN_MARRIAGE_DAYS}+ дн. и репутация {PET_MIN_COMBINED_REP}+)."

    age = _marriage_age_days(marriage["married_at"])
    if age < PET_MIN_MARRIAGE_DAYS:
        left = PET_MIN_MARRIAGE_DAYS - age
        return False, (
            f"⏳ Брак слишком молодой.\n"
            f"Нужно ещё <b>{left} дн.</b> (требуется {PET_MIN_MARRIAGE_DAYS} дн.)."
        )

    partner_id = marriage["partner_id"]
    my_stats = await get_user_stats(user_id, chat_id)
    partner_stats = await get_user_stats(partner_id, chat_id)
    my_rep      = (my_stats["reputation"]      if my_stats      else 0) or 0
    partner_rep = (partner_stats["reputation"] if partner_stats else 0) or 0
    combined = my_rep + partner_rep

    if combined < PET_MIN_COMBINED_REP:
        need = PET_MIN_COMBINED_REP - combined
        return False, (
            f"⭐ Не хватает репутации.\n"
            f"Совместная репутация: <b>{combined}</b> / {PET_MIN_COMBINED_REP} "
            f"(ещё нужно <b>{need}</b>)."
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
        marriage = await get_marriage(uid, chat_id)
        age = _marriage_age_days(marriage["married_at"]) if marriage else 0
        partner_id = marriage["partner_id"] if marriage else None
        my_stats = await get_user_stats(uid, chat_id)
        partner_stats = await get_user_stats(partner_id, chat_id) if partner_id else None
        my_rep      = ((my_stats["reputation"]      or 0) if my_stats      else 0)
        partner_rep = ((partner_stats["reputation"] or 0) if partner_stats else 0)
        combined = my_rep + partner_rep

        rep_bar = "█" * min(10, combined) + "░" * max(0, 10 - combined)
        age_bar = "█" * min(10, age)      + "░" * max(0, 10 - age)

        await message.answer(
            "🐾 <b>Питомец</b>\n\n"
            "Заведите питомца вместе с партнёром!\n\n"
            f"📋 <b>Условия:</b>\n"
            f"  💍 Возраст брака: <b>{age}</b> / {PET_MIN_MARRIAGE_DAYS} дн.  [{age_bar}]\n"
            f"  ⭐ Совм. репутация: <b>{combined}</b> / {PET_MIN_COMBINED_REP}  [{rep_bar}]\n\n"
            f"{reason if reason else ''}",
            parse_mode="HTML",
        )


async def _show_pet(message: Message, pet: dict, uid: int):
    ptype   = pet["pet_type"]
    emoji   = _PET_EMOJI.get(ptype, "🐾")
    kind    = _PET_NAME.get(ptype, "Питомец")
    name    = html.escape(pet["name"]) if pet.get("name") else f"<i>без имени</i>"
    age_days = (datetime.utcnow() - datetime.fromisoformat(pet["adopted_at"])).days

    await message.answer(
        f"{emoji} <b>Питомец: {name}</b>\n\n"
        f"🏷 Вид: {kind}\n"
        f"🎂 Возраст: <b>{age_days} дн.</b>\n\n"
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
        await message.answer(f"❌ <b>Нельзя завести питомца.</b>\n\n{reason}", parse_mode="HTML")
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


# ─── бот назвать питомца ──────────────────────────────────────────────────────

@router.message(BotCommand("назвать питомца", "питомец имя", "pet name"))
async def cmd_rename_pet(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Питомцы доступны только в группах.")
        return

    name = (cmd_args or "").strip()
    if not name:
        await message.answer(
            "❌ Укажи имя.\nПример: <code>бот назвать питомца Мурзик</code>",
            parse_mode="HTML",
        )
        return

    if len(name) > 32:
        await message.answer("❌ Имя слишком длинное (макс. 32 символа).")
        return

    uid     = message.from_user.id
    chat_id = message.chat.id
    found   = await rename_pet(uid, chat_id, name)
    if found:
        await message.answer(
            f"✅ Питомец переименован в <b>{html.escape(name)}</b>!",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "❌ Питомца нет. Сначала заведи его: <code>бот завести питомца</code>",
            parse_mode="HTML",
        )
