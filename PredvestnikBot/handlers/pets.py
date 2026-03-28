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

from config import PET_ADOPT_PRICE, PET_CHANGE_TYPE_PRICE, PET_MIN_MARRIAGE_DAYS, PET_MORA_SKIP_PRICE, PET_RENAME_PRICE
from database.db import (
    add_to_family_wallet,
    adopt_pet,
    add_mora,
    change_pet_type,
    deduct_mora,
    get_family_wallet,
    get_marriage,
    get_mora,
    get_pet,
    get_total_family_balance,
    get_user,
    rename_pet,
)
from handlers.economy import deduct_wallet
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
            f"Нужно ещё {left} дн. (требуется {PET_MIN_MARRIAGE_DAYS} дн.)."
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
            "🎉 <b>Питомец разблокировован!</b>\n\n"
            f"💰 Стоимость заведения: <b>{PET_ADOPT_PRICE} мора</b>\n\n"
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

    # Проверяем, первое это будет именование или переименование
    is_first_naming = pet.get("name") is None or pet.get("name") == ""
    rename_info = "Дать имя: <code>бот назвать питомца Мурзик</code> (бесплатно)" if is_first_naming else f"Переименовать: <code>бот назвать питомца Мурзик</code> ({PET_RENAME_PRICE} мора)"
    
    await message.answer(
        f"{emoji} <b>Питомец: {name}</b>\n\n"
        f"🏷 Вид: {kind}\n"
        f"🎂 Возраст: <b>{age}</b>\n\n"
        f"{rename_info}",
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
    await message.answer(
        f"🐾 <b>Заведение питомца</b>\n\n"
        f"💰 Стоимость: <b>{PET_ADOPT_PRICE} мора</b>\n\n"
        f"Выбери питомца:",
        parse_mode="HTML",
        reply_markup=kb
    )


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

    # Теперь показываем выбор оплаты
    emoji = _PET_EMOJI.get(ptype, "🐾")
    kind  = _PET_NAME.get(ptype, "Питомец")
    
    mora = await get_mora(uid, chat_id)
    personal_balance = mora["balance"] if mora else 0
    
    total_family_balance, _, _ = await get_total_family_balance(chat_id, uid)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"💰 Личный баланс ({personal_balance} мора)", 
            callback_data=f"pet_pay:{uid}:{ptype}:personal"
        )],
        [InlineKeyboardButton(
            text=f"👨‍👩‍👧‍👦 Семейный баланс ({total_family_balance} мора)", 
            callback_data=f"pet_pay:{uid}:{ptype}:family"
        )],
        [InlineKeyboardButton(text="❌ Отмена", callback_data=f"pet_cancel:{uid}")]
    ])
    
    try:
        await callback.message.edit_text(
            f"{emoji} <b>Завести {kind.lower()}а</b>\n\n"
            f"💰 Стоимость: <b>{PET_ADOPT_PRICE} мора</b>\n\n"
            f"Выберите способ оплаты:",
            parse_mode="HTML",
            reply_markup=kb
        )
    except Exception:
        pass
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("pet_pay:"))
async def cb_pet_pay(callback: CallbackQuery):
    """Обработка оплаты питомца."""
    parts = callback.data.split(":")
    owner = int(parts[1])
    ptype = parts[2]
    payment_type = parts[3]  # "personal" или "family"
    uid = callback.from_user.id
    chat_id = callback.message.chat.id

    if uid != owner:
        await callback.answer("❌ Это не твой выбор.", show_alert=True)
        return

    existing = await get_pet(uid, chat_id)
    if existing:
        await callback.answer("У тебя уже есть питомец!", show_alert=True)
        return

    marriage = await get_marriage(uid, chat_id)
    if not marriage:
        await callback.answer("❌ Нужно быть в браке!", show_alert=True)
        return

    partner_id = marriage["partner_id"]

    # Проверяем баланс и списываем атомарно
    if payment_type == "personal":
        mora = await get_mora(uid, chat_id)
        balance = mora["balance"] if mora else 0
        if balance < PET_ADOPT_PRICE:
            await callback.answer(
                f"❌ Недостаточно личной моры: {balance} / {PET_ADOPT_PRICE} 🪙",
                show_alert=True
            )
            return
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            cursor = await db.execute(
                "UPDATE user_mora SET balance=balance-? WHERE user_id=? AND chat_id=? AND balance>=?",
                (PET_ADOPT_PRICE, uid, chat_id, PET_ADOPT_PRICE),
            )
            if cursor.rowcount == 0:
                await callback.answer("❌ Не удалось списать Мору. Попробуй ещё раз.", show_alert=True)
                return
            await db.commit()
    else:  # family
        ok, new_bal = await deduct_wallet(uid, chat_id, PET_ADOPT_PRICE, "family")
        if not ok:
            await callback.answer(
                f"❌ Недостаточно Моры в семейном кошельке ({new_bal} / {PET_ADOPT_PRICE} 🪙)",
                show_alert=True
            )
            return

    # Заводим питомца
    await adopt_pet(uid, partner_id, chat_id, ptype)

    emoji = _PET_EMOJI.get(ptype, "🐾")
    kind = _PET_NAME.get(ptype, "Питомец")

    partner = await get_user(partner_id)
    partner_name = html.escape(partner["full_name"]) if partner else str(partner_id)

    payment_text = "личного" if payment_type == "personal" else "семейного"

    try:
        await callback.message.edit_text(
            f"{emoji} <b>Поздравляем!</b>\n\n"
            f"Вы с {user_mention(partner_id, partner_name)} завели <b>{kind.lower()}а</b>! 🎉\n\n"
            f"💰 Стоимость {PET_ADOPT_PRICE} мора списана с {payment_text} баланса.\n\n"
            f"Дайте ему имя: <code>бот назвать питомца Мурзик</code>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer(f"{emoji} Питомец заведён!")


@router.callback_query(lambda c: c.data and c.data.startswith("pet_cancel:"))
async def cb_pet_cancel(callback: CallbackQuery):
    """Отмена заведения питомца."""
    owner = int(callback.data.split(":")[1])
    uid = callback.from_user.id

    if uid != owner:
        await callback.answer("❌ Это не твоя кнопка!", show_alert=True)
        return

    try:
        await callback.message.edit_text("❌ Заведение питомца отменено.")
    except Exception:
        pass
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("pet_rename_confirm:"))
async def cb_pet_rename_confirm(callback: CallbackQuery):
    """Подтверждение переименования питомца."""
    data_parts = callback.data.split(":", 2)
    owner = int(data_parts[1])
    name = data_parts[2]
    uid = callback.from_user.id
    chat_id = callback.message.chat.id

    if uid != owner:
        await callback.answer("❌ Это не твоя кнопка!", show_alert=True)
        return

    # Проверяем и списываем Мору за переименование
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    if bal < PET_RENAME_PRICE:
        await callback.answer(
            f"❌ Недостаточно моры: {bal} / {PET_RENAME_PRICE} 🪙",
            show_alert=True,
        )
        return

    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE user_mora SET balance=balance-? WHERE user_id=? AND chat_id=? AND balance>=?",
            (PET_RENAME_PRICE, uid, chat_id, PET_RENAME_PRICE),
        )
        if cursor.rowcount == 0:
            await callback.answer("❌ Не удалось списать Мору. Попробуй ещё раз.", show_alert=True)
            return
        await db.commit()
        async with db.execute(
            "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
            (uid, chat_id),
        ) as c:
            row = await c.fetchone()
        new_bal = row[0] if row else 0

    found = await rename_pet(uid, chat_id, name)
    if found:
        try:
            await callback.message.edit_text(
                f"✅ Питомец переименован в <b>{html.escape(name)}</b>! (<b>-{PET_RENAME_PRICE} 🪙</b>)\n"
                f"Твой баланс: <b>{new_bal} 🪙</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        await callback.answer("✅ Переименование завершено!")
    else:
        # Возвращаем деньги, если не удалось переименовать
        await add_mora(uid, chat_id, PET_RENAME_PRICE)
        await callback.answer("❌ Не удалось переименовать питомца.", show_alert=True)


@router.callback_query(lambda c: c.data and c.data.startswith("pet_rename_cancel:"))
async def cb_pet_rename_cancel(callback: CallbackQuery):
    """Отмена переименования питомца."""
    owner = int(callback.data.split(":")[1])
    uid = callback.from_user.id

    if uid != owner:
        await callback.answer("❌ Это не твоя кнопка!", show_alert=True)
        return

    try:
        await callback.message.edit_text("❌ Переименование питомца отменено.")
    except Exception:
        pass
    await callback.answer()


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

    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE user_mora SET balance=balance-? WHERE user_id=? AND chat_id=? AND balance>=?",
            (PET_MORA_SKIP_PRICE, uid, chat_id, PET_MORA_SKIP_PRICE),
        )
        if cursor.rowcount == 0:
            await callback.answer("❌ Не удалось списать Мору.", show_alert=True)
            return
        await db.commit()
        async with db.execute(
            "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
            (uid, chat_id),
        ) as c:
            row = await c.fetchone()
        new_bal = row[0] if row else 0

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🐱 Котёнок", callback_data=f"pet_adopt_skip:{uid}:cat"),
        InlineKeyboardButton(text="🐶 Щенок",   callback_data=f"pet_adopt_skip:{uid}:dog"),
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


@router.callback_query(lambda c: c.data and c.data.startswith("pet_adopt_skip:"))
async def cb_pet_adopt_after_skip(callback: CallbackQuery):
    """Выбор типа питомца после оплаченного пропуска ожидания.
    Возраст брака НЕ проверяется — пользователь уже заплатил за пропуск.
    Дополнительная оплата НЕ взимается — скип-цена уже включает всё.
    """
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

    marriage = await get_marriage(uid, chat_id)
    if not marriage:
        await callback.answer("❌ Нужно быть в браке!", show_alert=True)
        return

    partner_id = marriage["partner_id"]

    # Сразу заводим питомца — доп. оплата не нужна, скип уже оплачен
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
            f"❌ Укажи имя.\nПример: <code>бот назвать питомца Мурзик</code>",
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

    # Проверяем, первое это именование или переименование
    is_first_naming = pet["name"] is None or pet["name"] == ""
    
    if is_first_naming:
        # Первое именование бесплатно
        found = await rename_pet(uid, chat_id, name)
        if found:
            await message.answer(
                f"✅ Питомец получил имя <b>{html.escape(name)}</b>! 🎉\n"
                f"(Первое именование бесплатно)",
                parse_mode="HTML",
            )
        else:
            await message.answer("❌ Не удалось дать имя питомцу. Попробуй ещё раз.")
    else:
        # Переименование платное - показываем предупреждение
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💰 Переименовать за {PET_RENAME_PRICE} мора", 
                callback_data=f"pet_rename_confirm:{uid}:{name}"
            )],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"pet_rename_cancel:{uid}")]
        ])
        
        mora = await get_mora(uid, chat_id)
        bal = mora["balance"] if mora else 0
        
        current_name = html.escape(pet["name"])
        new_name = html.escape(name)
        
        if bal < PET_RENAME_PRICE:
            await message.answer(
                f"❌ Для переименования питомца нужно <b>{PET_RENAME_PRICE} 🪙</b>.\n"
                f"У тебя: <b>{bal} 🪙</b>.",
                parse_mode="HTML",
            )
        else:
            await message.answer(
                f"🔄 Переименование питомца\n\n"
                f"Текущее имя: <b>{current_name}</b>\n"
                f"Новое имя: <b>{new_name}</b>\n\n"
                f"💰 <b>Стоимость: {PET_RENAME_PRICE} мора</b>\n"
                f"Ваш баланс: <b>{bal} мора</b>\n\n"
                f"⚠️ Переименование платное! Подтвердите операцию:",
                parse_mode="HTML",
                reply_markup=kb
            )


# ─── Смена вида питомца (платная, обычные пользователи) ───────────────────────

@router.message(BotCommand("сменить вид питомца", "сменить питомца", "поменять питомца", "смена вида питомца"))
async def cmd_change_pet_type(message: Message, cmd_args: str):
    if message.chat.type == "private":
        await message.answer("❌ Питомцы доступны только в группах.")
        return
    uid = message.from_user.id
    chat_id = message.chat.id
    try:
        pet = await get_pet(uid, chat_id)
        if not pet:
            await message.answer("❌ У тебя нет питомца.")
            return

        arg = (cmd_args or "").strip().lower()
        type_map = {
            "кот": "cat", "кошка": "cat", "котёнок": "cat", "котенок": "cat", "cat": "cat",
            "собака": "dog", "собак": "dog", "щенок": "dog", "dog": "dog", "пёс": "dog", "пес": "dog",
        }
        new_type = type_map.get(arg)
        if not new_type:
            await message.answer(
                f"🐾 <b>Смена вида питомца</b>\n\n"
                f"Укажи нового питомца:\n"
                f"  <code>бот сменить вид питомца кот</code>\n"
                f"  <code>бот сменить вид питомца собака</code>\n\n"
                f"💰 Стоимость: <b>{PET_CHANGE_TYPE_PRICE} 🪙</b>",
                parse_mode="HTML",
            )
            return

        if pet["pet_type"] == new_type:
            await message.answer(f"❌ У тебя уже {_PET_NAME.get(new_type, 'этот питомец')}!")
            return

        mora = await get_mora(uid, chat_id)
        bal = mora["balance"] if mora else 0
        if bal < PET_CHANGE_TYPE_PRICE:
            await message.answer(
                f"❌ Недостаточно Моры!\n"
                f"Нужно: <b>{PET_CHANGE_TYPE_PRICE} 🪙</b>\n"
                f"У тебя: <b>{bal} 🪙</b>",
                parse_mode="HTML",
            )
            return

        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            cursor = await db.execute(
                "UPDATE user_mora SET balance=balance-? WHERE user_id=? AND chat_id=? AND balance>=?",
                (PET_CHANGE_TYPE_PRICE, uid, chat_id, PET_CHANGE_TYPE_PRICE),
            )
            if cursor.rowcount == 0:
                await message.answer("❌ Не удалось списать Мору.")
                return
            await db.commit()
            async with db.execute(
                "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
                (uid, chat_id),
            ) as c:
                row = await c.fetchone()
            new_bal = row[0] if row else 0

        await change_pet_type(uid, chat_id, new_type)
        old_emoji = _PET_EMOJI.get(pet["pet_type"], "🐾")
        new_emoji = _PET_EMOJI.get(new_type, "🐾")
        old_name  = _PET_NAME.get(pet["pet_type"], "?")
        new_name  = _PET_NAME.get(new_type, "?")
        await message.answer(
            f"✅ <b>Вид питомца изменён!</b>\n\n"
            f"{old_emoji} {old_name} → {new_emoji} {new_name}\n\n"
            f"💰 Баланс: <b>{new_bal} 🪙</b>",
            parse_mode="HTML",
        )
    except Exception:
        await message.answer("❌ Произошла ошибка при смене вида питомца.")


# ─── бот прогулка ─────────────────────────────────────────────────────────────

@router.message(BotCommand("прогулка", "гулять", "walk"))
async def cmd_pet_walk(message: Message, cmd_args: str):
    """бот прогулка — отправить питомца гулять на 3 часа."""
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    pet = await get_pet(uid, chat_id)
    if not pet:
        await message.answer(
            "❌ У тебя нет питомца.\n"
            "Заведи его: <code>бот завести питомца</code>",
            parse_mode="HTML",
        )
        return

    from services.pet_service import walk as pet_walk
    from services.exceptions import PetAlreadyWalkingError, PetNotFoundError
    try:
        result = await pet_walk(uid, chat_id)
    except PetAlreadyWalkingError as e:
        h, m = divmod(e.mins_left, 60)
        time_str = f"{h} ч {m} мин" if h else f"{m} мин"
        ptype = pet.get("pet_type", "")
        emoji = _PET_EMOJI.get(ptype, "🐾")
        await message.answer(
            f"{emoji} <b>{html.escape(pet.get('name') or 'Питомец')}</b> уже на прогулке!\n"
            f"⏳ Вернётся через <b>{time_str}</b>.",
            parse_mode="HTML",
        )
        return
    except PetNotFoundError as e:
        await message.answer(f"❌ {e}")
        return

    ptype = result.get("pet_type") or pet.get("pet_type", "")
    emoji = _PET_EMOJI.get(ptype, "🐾")
    pet_name = html.escape(result.get("pet_name") or pet.get("name") or "Питомец")
    old_fatigue = pet.get("fatigue") or 0
    new_fatigue = result.get("fatigue", max(0, old_fatigue - 30))
    reward = result.get("reward", 0)
    partner_line = f"\n💕 Партнёр получил <b>+{reward} 🪙</b>" if result.get("partner_rewarded") else ""
    await message.answer(
        f"{emoji} <b>{pet_name}</b> пошёл гулять на <b>3 часа</b>!\n"
        f"😴 Усталость: {old_fatigue} → <b>{new_fatigue}</b>\n"
        f"🪙 Награда: <b>+{reward} 🪙</b>{partner_line}\n\n"
        f"<i>Питомец вернётся автоматически. Проверь статус в Mini App.</i>",
        parse_mode="HTML",
    )
