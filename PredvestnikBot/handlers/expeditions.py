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

from config import EXPEDITION_OPTIONS, MINI_APP_TG_URL
from database.db import (
    add_mora,
    add_pet_fatigue,
    add_to_family_wallet,
    get_active_expedition,
    get_family_wallet,
    get_marriage,
    get_mora,
    get_pet,
    get_pet_fatigue,
    get_total_family_balance,
    start_expedition,
)
from filters.bot_command import BotCommand
from handlers.economy import deduct_wallet
from utils.helpers import user_mention

from filters.chat_mode import MainChatOnly
router = Router()
router.message.filter(MainChatOnly())
router.callback_query.filter(MainChatOnly())



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

    # PHASE 3: Expeditions → Mini App in groups
    abs_cid = abs(message.chat.id)
    btn = InlineKeyboardButton(
        text="🏕 Экспедиции в Mini App",
        url=f"{MINI_APP_TG_URL}?startapp={abs_cid}_expedition",
    )
    await message.answer(
        "🏕 <b>Экспедиции переехали в Mini App!</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]),
    )
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

    # Проверяем усталость питомца
    fatigue = pet.get("fatigue") or await get_pet_fatigue(uid, chat_id)
    pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet["pet_type"], "🐾")
    pet_name = html.escape(pet["name"]) if pet.get("name") else "безымянный"
    if fatigue >= 100:
        await message.answer(
            f"{pet_emoji} <b>{pet_name}</b> полностью измотан и не может идти в экспедицию!\n\n"
            f"😴 Усталость: <b>{fatigue}/100</b>\n"
            f"🍖 Покорми питомца командой <code>бот еда</code> чтобы снизить усталость.",
            parse_mode="HTML",
        )
        return
    if fatigue >= 80:
        await message.answer(
            f"⚠️ {pet_emoji} <b>{pet_name}</b> очень устал!\n"
            f"😓 Усталость: <b>{fatigue}/100</b> — рекомендуем покормить его перед следующим походом.\n",
            parse_mode="HTML",
        )

    # Проверяем, не в экспедиции ли уже
    active = await get_active_expedition(uid, chat_id)
    if active:
        left = _time_left(active["started_at"], active["duration_h"])
        await message.answer(
            f"🗺 <b>Питомец в экспедиции</b>\n\n"
            f"{pet_emoji} <b>{pet_name}</b> сейчас в походе.\n"
            f"⏳ Осталось: <b>{left}</b>\n"
            f"💰 Награда: <b>{active['reward_min']}–{active['reward_max']} 🪙</b>",
            parse_mode="HTML",
        )
        return

    # Проверяем брак для выбора кошелька
    marriage = await get_marriage(uid, chat_id)
    
    # Показываем меню выбора кошелька (если в браке) или сразу экспедицию
    if marriage:
        mora = await get_mora(uid, chat_id)
        personal_bal = mora["balance"] if mora else 0
        total_family_bal, _, _ = await get_total_family_balance(chat_id, uid)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💰 Личный кошелёк ({personal_bal} 🪙)",
                callback_data=f"exped_wallet:{uid}:personal"
            )],
            [InlineKeyboardButton(
                text=f"👨‍👩‍👧 Семейный кошелёк ({total_family_bal} 🪙)", 
                callback_data=f"exped_wallet:{uid}:family"
            )]
        ])
        
        pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet["pet_type"], "🐾")
        pet_name = html.escape(pet["name"]) if pet.get("name") else "безымянный"
        await message.answer(
            f"🗺 <b>Экспедиция</b>\n\n"
            f"Отправь {pet_emoji} <b>{pet_name}</b> в поход за Морой!\n\n"
            f"💳 Выбери кошелёк для оплаты:",
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        # Одинокий игрок — только личный кошелёк
        await _show_expedition_menu(message, uid, "personal")


async def _show_expedition_menu(message: Message, uid: int, wallet_type: str):
    """Показывает меню выбора экспедиции с учётом выбранного кошелька."""
    chat_id = message.chat.id
    
    if wallet_type == "personal":
        mora = await get_mora(uid, chat_id)
        balance = mora["balance"] if mora else 0
        wallet_icon = "💰"
        wallet_name = "личного кошелька"
    else:  # family
        total_family_bal, _, _ = await get_total_family_balance(chat_id, uid)
        balance = total_family_bal
        wallet_icon = "👨‍👩‍👧"
        wallet_name = "семейного кошелька"
    
    rows = []
    for key, opt in EXPEDITION_OPTIONS.items():
        cost_text = f"{opt['cost']} 🪙" if opt["cost"] > 0 else "бесплатно"
        # Проверяем, хватает ли денег
        can_afford = balance >= opt["cost"] if opt["cost"] > 0 else True
        prefix = "🗺" if can_afford else "🚫"
        rows.append([InlineKeyboardButton(
            text=f"{prefix} {opt['label']} — {cost_text} (награда {opt['reward_min']}–{opt['reward_max']})",
            callback_data=f"exped:{uid}:{key}:{wallet_type}",
        )])
    
    # Кнопка "Назад" если это семья
    marriage = await get_marriage(uid, chat_id)
    if marriage:
        rows.append([InlineKeyboardButton(
            text="🔙 Выбрать другой кошелёк",
            callback_data=f"exped_wallet:{uid}:back"
        )])
    
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    
    pet = await get_pet(uid, chat_id)
    pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet["pet_type"], "🐾")
    pet_name = html.escape(pet["name"]) if pet.get("name") else "безымянный"
    
    try:
        await message.edit_text(
            f"🗺 <b>Экспедиция</b>\n\n"
            f"Отправь {pet_emoji} <b>{pet_name}</b> в поход за Морой!\n"
            f"{wallet_icon} Баланс {wallet_name}: <b>{balance} 🪙</b>\n\n"
            f"Выбери длительность:",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except AttributeError:
        # Если это обычное сообщение, не callback
        await message.answer(
            f"🗺 <b>Экспедиция</b>\n\n"
            f"Отправь {pet_emoji} <b>{pet_name}</b> в поход за Морой!\n"
            f"{wallet_icon} Баланс {wallet_name}: <b>{balance} 🪙</b>\n\n"
            f"Выбери длительность:",
            parse_mode="HTML",
            reply_markup=kb,
        )


@router.callback_query(lambda c: c.data and c.data.startswith("exped_wallet:"))
async def cb_expedition_wallet_choice(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    choice = parts[2]
    
    if callback.from_user.id != owner:
        await callback.answer("❌ Это не твоя кнопка!", show_alert=True)
        return
    
    if choice == "back":
        # Возвращаемся к выбору кошелька
        uid = owner
        chat_id = callback.message.chat.id
        marriage = await get_marriage(uid, chat_id)
        
        mora = await get_mora(uid, chat_id)
        personal_bal = mora["balance"] if mora else 0
        total_family_bal, _, _ = await get_total_family_balance(chat_id, uid)
        
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text=f"💰 Личный кошелёк ({personal_bal} 🪙)",
                callback_data=f"exped_wallet:{uid}:personal"
            )],
            [InlineKeyboardButton(
                text=f"👨‍👩‍👧 Семейный кошелёк ({total_family_bal} 🪙)", 
                callback_data=f"exped_wallet:{uid}:family"
            )]
        ])
        
        pet = await get_pet(uid, chat_id)
        pet_emoji = {"cat": "🐱", "dog": "🐶"}.get(pet["pet_type"], "🐾")
        pet_name = html.escape(pet["name"]) if pet.get("name") else "безымянный"
        
        try:
            await callback.message.edit_text(
                f"🗺 <b>Экспедиция</b>\n\n"
                f"Отправь {pet_emoji} <b>{pet_name}</b> в поход за Морой!\n\n"
                f"💳 Выбери кошелёк для оплаты:",
                parse_mode="HTML",
                reply_markup=kb,
            )
        except Exception:
            pass
        await callback.answer()
        return
    
    # Переходим к выбору экспедиции
    await _show_expedition_menu(callback.message, owner, choice)
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("exped:"))
async def cb_expedition_start(callback: CallbackQuery):
    parts = callback.data.split(":")
    owner = int(parts[1])
    key = parts[2]
    wallet_type = parts[3] if len(parts) > 3 else "personal"

    if callback.from_user.id != owner:
        await callback.answer("❌ Это не твоя кнопка!", show_alert=True)
        return

    chat_id = callback.message.chat.id
    uid = owner

    opt = EXPEDITION_OPTIONS.get(key)
    if not opt:
        await callback.answer("❌ Неизвестный вариант.", show_alert=True)
        return

    from api.expeditions import start_expedition as _api_start
    try:
        res = await _api_start(uid, chat_id, key, wallet_type)
    except ValueError as e:
        await callback.answer(str(e), show_alert=True)
        return

    # Fetch pet only for display (validation already done in api)
    pet = await get_pet(uid, chat_id)
    pet_emoji  = {"cat": "🐱", "dog": "🐶"}.get((pet or {}).get("pet_type", ""), "🐾")
    pet_name   = html.escape((pet or {}).get("name") or "безымянный")
    cost_text  = f"Списано <b>{res['cost']} 🪙</b>" if res["cost"] > 0 else "Бесплатно"

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

    # Quest chat notification
    if res.get("quest_done"):
        try:
            name = html.escape(callback.from_user.full_name)
            await callback.message.answer(
                f"🎉 {name} выполнил ежедневное задание! "
                f"<b>+{res['quest_xp']} XP</b>  <b>+{res['quest_mora']} Моры</b> 🪙",
                parse_mode="HTML",
            )
        except Exception:
            pass
