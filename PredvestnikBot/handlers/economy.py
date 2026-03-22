"""
Команды экономики: валюта Мора.

  бот баланс              — твой баланс в этом чате
  бот баланс @user        — баланс другого пользователя (только если открыт)
  бот купить вип          — купить VIP статус за 1000 Мора
  бот вип @user вкл/выкл  — выдать/снять VIP (администратор+)
  бот купить буст         — купить буст XP x2 на время
  бот рамки               — доступные рамки профиля для топа
  бот купить рамку [ключ] — купить и активировать рамку
  бот семейный кошелёк    — посмотреть семейный баланс
  бот пополнить семью N   — перевести N Моры в семейный кошелёк
  бот снять семью N       — забрать N Моры из семейного кошелька
  бот анонимка [текст]    — анонимное сообщение в чат администрации (50 Мора)
"""
import html
import random
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import (
    add_mora,
    add_to_family_wallet,
    deduct_mora,
    get_admin_group_ids,
    get_family_wallet,
    get_mora,
    get_top_frame,
    get_user,
    get_vip,
    get_xp_boost_active,
    set_mora_public,
    set_top_frame,
    set_vip,
    set_xp_boost,
    get_marriage,
)
from config import (
    ANON_MSG_PRICE,
    VIP_PRICE,
)
from filters.bot_command import BotCommand
from filters.rank_filter import RankFilter
from utils.helpers import resolve_target, user_mention
from utils.ranks import rank_level

router = Router()

# ─── Рамки профиля в топе ─────────────────────────────────────────────────────
#  (ключ, emoji, название, цена в Море, описание)
TOP_FRAMES: list[tuple[str, str, str, int, str]] = [
    ("default",  "🔰", "Стандарт",   0,    "Базовая рамка (бесплатно)"),
    ("warrior",  "⚔️", "Воин",        500,  "Для тех, кто не отступает"),
    ("king",     "👑", "Король",      1000, "Только для избранных"),
    ("moon",     "🌙", "Ночной",      800,  "Загадочная ночная рамка"),
    ("fire",     "🔥", "Огненный",    700,  "Яркая и горячая"),
    ("diamond",  "💎", "Алмазный",    1200, "Премиальная рамка для VIP"),
    ("star",     "⭐", "Звёздный",    600,  "Рамка победителей"),
]

_FRAME_MAP: dict[str, tuple] = {f[0]: f for f in TOP_FRAMES}


def _frame_emoji(key: str | None) -> str:
    if not key:
        return ""
    entry = _FRAME_MAP.get(key)
    return entry[1] if entry else ""


# ─── XP Буст ──────────────────────────────────────────────────────────────────
#  (ключ, часов, цена, метка)
XP_BOOST_OPTIONS: list[tuple[str, int, int, str]] = [
    ("1h",  1,  75,  "1 ч"),
    ("2h",  2,  140, "2 ч"),
    ("4h",  4,  260, "4 ч"),
    ("8h",  8,  480, "8 ч"),
    ("24h", 24, 1000, "1 день"),
]

_BOOST_MAP: dict[str, tuple] = {b[0]: b for b in XP_BOOST_OPTIONS}


# ─── Баланс ───────────────────────────────────────────────────────────────────

def _mora_text(balance: int, total: int, streak: int, public: int, vip: int = 0, boost: bool = False, frame: str | None = None) -> str:
    streak_line = f"\n🔥 Стрик: <b>{streak} дн.</b>" if streak > 0 else ""
    privacy_line = "🔓 Баланс виден другим" if public else "🔒 Баланс скрыт от других"
    vip_line = "\n💎 <b>VIP статус активен</b>" if vip else ""
    boost_line = "\n⚡ <b>Буст XP x2 активен</b>" if boost else ""
    frame_label = _FRAME_MAP.get(frame, ("", "", frame or "—"))[2] if frame else "—"
    frame_emoji_str = _frame_emoji(frame)
    return (
        f"💰 <b>Твой баланс</b>{vip_line}\n\n"
        f"Мора: <b>{balance} 🪙</b>\n"
        f"Всего заработано: {total} 🪙"
        f"{streak_line}\n"
        f"🖼 Рамка: {frame_emoji_str} {frame_label}"
        f"{boost_line}\n\n"
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
        uid, name, _ = await resolve_target(message, arg)
        if uid is None:
            await message.answer(name)
            return

        mora = await get_mora(uid, chat_id)
        balance = (mora["balance"] or 0) if mora else 0
        total   = (mora["total_earned"] or 0) if mora else 0
        user    = await get_user(uid)
        display = html.escape(user["full_name"]) if user else html.escape(name)
        vip_badge = " 💎" if mora and (mora["vip"] or 0) else ""
        await message.answer(
            f"💰 <b>Баланс</b>{vip_badge} {user_mention(uid, display)}\n\n"
            f"Мора: <b>{balance} 🪙</b>\n"
            f"Всего заработано: {total} 🪙",
            parse_mode="HTML",
        )
        return

    uid    = message.from_user.id
    mora   = await get_mora(uid, chat_id)
    bal    = mora["balance"]     if mora else 0
    total  = mora["total_earned"] if mora else 0
    streak = mora["streak_days"] if mora else 0
    public = mora["mora_public"] if mora else 0
    vip    = mora["vip"]         if mora else 0
    frame  = mora["top_frame"]   if mora else None
    boost  = await get_xp_boost_active(uid, chat_id)

    await message.answer(
        _mora_text(bal, total, streak, public, vip, boost, frame),
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
    vip    = mora["vip"]          if mora else 0
    frame  = mora["top_frame"]    if mora else None
    boost  = await get_xp_boost_active(uid, chat_id)

    try:
        await callback.message.edit_text(
            _mora_text(bal, total, streak, new_val, vip, boost, frame),
            parse_mode="HTML",
            reply_markup=_mora_keyboard(uid, new_val),
        )
    except Exception:
        pass
    await callback.answer("✅ Настройки обновлены!")


# ─── VIP Статус ───────────────────────────────────────────────────────────────


@router.message(BotCommand("купить вип", "купить vip", "vip", "вип"))
async def cmd_buy_vip(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    if await get_vip(uid, chat_id):
        await message.answer("💎 У тебя уже есть VIP статус!")
        return

    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    if bal < VIP_PRICE:
        await message.answer(
            f"💎 <b>VIP статус</b> стоит <b>{VIP_PRICE} Моры</b>.\n\n"
            f"У тебя: <b>{bal} 🪙</b> — недостаточно.\n"
            f"Зарабатывай Мору, общаясь в чате!",
            parse_mode="HTML",
        )
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"✅ Купить за {VIP_PRICE} Моры", callback_data=f"buy_vip:{uid}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"buy_cancel:{uid}"),
    ]])
    await message.answer(
        f"💎 <b>VIP Статус</b>\n\n"
        f"Стоимость: <b>{VIP_PRICE} 🪙</b>\n"
        f"Твой баланс: <b>{bal} 🪙</b>\n\n"
        f"Что даёт VIP:\n"
        f"  💎 Значок VIP в профиле и топе\n"
        f"  👑 Красивое оформление профиля\n"
        f"  🔮 Доступ к рамке «Алмазный» для топа",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("buy_vip:"))
async def cb_buy_vip(callback: CallbackQuery):
    parts = callback.data.split(":")
    uid = int(parts[1])

    if callback.from_user.id != uid:
        await callback.answer("🚫 Это не твоя кнопка!", show_alert=True)
        return

    chat_id = callback.message.chat.id

    if await get_vip(uid, chat_id):
        await callback.answer("💎 У тебя уже есть VIP!", show_alert=True)
        return

    ok, new_bal = await deduct_mora(uid, chat_id, VIP_PRICE)
    if not ok:
        mora = await get_mora(uid, chat_id)
        bal = mora["balance"] if mora else 0
        await callback.answer(f"❌ Недостаточно Моры! ({bal} / {VIP_PRICE})", show_alert=True)
        return

    await set_vip(uid, chat_id, 1)
    try:
        await callback.message.edit_text(
            f"💎 <b>VIP получен!</b>\n\n"
            f"Поздравляем! Твой баланс: <b>{new_bal} 🪙</b>\n\n"
            f"Значок 💎 теперь отображается в профиле и топе.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer("💎 VIP активирован!")


@router.message(BotCommand("выдать вип", "вип выдать", "вип управление"), RankFilter("admin_junior"))
async def cmd_admin_vip(message: Message, cmd_args: str):
    """Admin command: бот выдать вип @user вкл/выкл"""
    if message.chat.type not in ("group", "supergroup"):
        return
    parts = (cmd_args or "").strip().split()
    if len(parts) < 2:
        await message.answer(
            "Использование: <code>бот выдать вип @user вкл</code> или <code>бот выдать вип @user выкл</code>",
            parse_mode="HTML",
        )
        return
    # Определяем target и действие
    target_str = parts[0]
    action_str = parts[-1].lower()
    uid, name, _ = await resolve_target(message, target_str)
    if uid is None:
        await message.answer(name)
        return
    if action_str in ("вкл", "on", "1"):
        await set_vip(uid, message.chat.id, 1)
        user = await get_user(uid)
        display = html.escape(user["full_name"]) if user else name
        await message.answer(f"✅ 💎 VIP выдан: {user_mention(uid, display)}", parse_mode="HTML")
    elif action_str in ("выкл", "off", "0"):
        await set_vip(uid, message.chat.id, 0)
        user = await get_user(uid)
        display = html.escape(user["full_name"]) if user else name
        await message.answer(f"✅ VIP снят: {user_mention(uid, display)}", parse_mode="HTML")
    else:
        await message.answer("❌ Укажи <code>вкл</code> или <code>выкл</code>.", parse_mode="HTML")


@router.callback_query(F.data.startswith("buy_cancel:"))
async def cb_buy_cancel(callback: CallbackQuery):
    if callback.from_user.id != int(callback.data.split(":")[1]):
        await callback.answer("🚫", show_alert=True)
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer("Отменено.")


# ─── XP Буст ──────────────────────────────────────────────────────────────────

@router.message(BotCommand("купить буст", "буст", "xp boost", "boost"))
async def cmd_buy_boost(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id

    boost_active = await get_xp_boost_active(uid, chat_id)
    if boost_active:
        await message.answer("⚡ У тебя уже активен буст XP x2!")
        return

    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0

    rows = []
    for key, hours, price, label in XP_BOOST_OPTIONS:
        rows.append([InlineKeyboardButton(
            text=f"⚡ {label} — {price} 🪙",
            callback_data=f"boost_buy:{uid}:{key}",
        )])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"buy_cancel:{uid}")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await message.answer(
        f"⚡ <b>Буст XP x2</b>\n\n"
        f"Делает все начисления XP вдвое больше на выбранное время.\n"
        f"Твой баланс: <b>{bal} 🪙</b>\n\n"
        f"Выбери продолжительность:",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("boost_buy:"))
async def cb_boost_buy(callback: CallbackQuery):
    parts = callback.data.split(":")
    uid = int(parts[1])
    key = parts[2]

    if callback.from_user.id != uid:
        await callback.answer("🚫 Это не твоя кнопка!", show_alert=True)
        return

    chat_id = callback.message.chat.id
    entry = _BOOST_MAP.get(key)
    if not entry:
        await callback.answer("❌ Неизвестный вариант.", show_alert=True)
        return

    _, hours, price, label = entry

    if await get_xp_boost_active(uid, chat_id):
        await callback.answer("⚡ Буст уже активен!", show_alert=True)
        return

    ok, new_bal = await deduct_mora(uid, chat_id, price)
    if not ok:
        mora = await get_mora(uid, chat_id)
        bal = mora["balance"] if mora else 0
        await callback.answer(f"❌ Недостаточно Моры! ({bal} / {price})", show_alert=True)
        return

    until = (datetime.utcnow() + timedelta(hours=hours)).isoformat()
    await set_xp_boost(uid, chat_id, until)
    try:
        await callback.message.edit_text(
            f"⚡ <b>Буст XP x2 активирован!</b>\n\n"
            f"Продолжительность: <b>{label}</b>\n"
            f"Твой баланс: <b>{new_bal} 🪙</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer(f"⚡ Буст на {label} активирован!")


# ─── Рамки профиля в топе ─────────────────────────────────────────────────────

@router.message(BotCommand("рамки", "рамка", "frames", "frame"))
async def cmd_frames(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    current_frame = mora["top_frame"] if mora else None

    lines = ["🖼 <b>Рамки профиля в топе</b>\n\n"]
    for key, emoji, name, price, desc in TOP_FRAMES:
        active = " ◀ активна" if key == current_frame else ""
        price_str = "бесплатно" if price == 0 else f"{price} 🪙"
        lines.append(f"{emoji} <b>{name}</b> — {price_str}{active}\n  <i>{desc}</i>")

    lines.append(f"\nТвой баланс: <b>{bal} 🪙</b>")
    lines.append("\nКупить: <code>бот купить рамку [название]</code>")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(BotCommand("купить рамку", "рамку", "купить frame"))
async def cmd_buy_frame(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    arg = (cmd_args or "").strip().lower()

    if not arg:
        rows = []
        for key, emoji, name, price, _ in TOP_FRAMES:
            price_str = "бесплатно" if price == 0 else f"{price} 🪙"
            rows.append([InlineKeyboardButton(
                text=f"{emoji} {name} — {price_str}",
                callback_data=f"frame_buy:{uid}:{key}",
            )])
        rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"buy_cancel:{uid}")])
        mora = await get_mora(uid, chat_id)
        bal = mora["balance"] if mora else 0
        await message.answer(
            f"🖼 <b>Выбери рамку</b>\n\nТвой баланс: <b>{bal} 🪙</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    # Поиск по ключу или названию
    found = None
    for key, emoji, name, price, desc in TOP_FRAMES:
        if arg in (key, name.lower()):
            found = (key, emoji, name, price, desc)
            break

    if not found:
        await message.answer(
            f"❌ Рамка не найдена. Доступные: {', '.join(f[2] for f in TOP_FRAMES)}",
            parse_mode="HTML",
        )
        return

    key, emoji, name, price, desc = found
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"✅ {('Активировать' if price == 0 else f'Купить за {price} Моры')}", callback_data=f"frame_buy:{uid}:{key}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"buy_cancel:{uid}"),
    ]])
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    await message.answer(
        f"{emoji} <b>{name}</b>\n{desc}\n\nЦена: {price} 🪙\nТвой баланс: {bal} 🪙",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("frame_buy:"))
async def cb_frame_buy(callback: CallbackQuery):
    parts = callback.data.split(":")
    uid = int(parts[1])
    key = parts[2]

    if callback.from_user.id != uid:
        await callback.answer("🚫 Это не твоя кнопка!", show_alert=True)
        return

    chat_id = callback.message.chat.id
    entry = _FRAME_MAP.get(key)
    if not entry:
        await callback.answer("❌ Неизвестная рамка.", show_alert=True)
        return

    fkey, emoji, fname, price, _ = entry

    mora = await get_mora(uid, chat_id)
    current = mora["top_frame"] if mora else None
    if current == fkey:
        await callback.answer("Эта рамка уже активна!", show_alert=True)
        return

    if price > 0:
        ok, new_bal = await deduct_mora(uid, chat_id, price)
        if not ok:
            bal = mora["balance"] if mora else 0
            await callback.answer(f"❌ Недостаточно Моры! ({bal} / {price})", show_alert=True)
            return
    else:
        new_bal = mora["balance"] if mora else 0

    await set_top_frame(uid, chat_id, fkey)
    try:
        await callback.message.edit_text(
            f"{emoji} <b>Рамка «{fname}» активирована!</b>\n\n"
            f"Теперь она будет отображаться в топе чата.\n"
            f"Твой баланс: <b>{new_bal} 🪙</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    await callback.answer(f"{emoji} Рамка «{fname}» активирована!")


# ─── Семейный кошелёк ─────────────────────────────────────────────────────────

async def _get_partner_id(user_id: int, chat_id: int) -> int | None:
    marriage = await get_marriage(user_id, chat_id)
    return marriage["partner_id"] if marriage else None


@router.message(BotCommand("семейный кошелёк", "семейный баланс", "family wallet", "семья кошелёк"))
async def cmd_family_wallet(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    partner_id = await _get_partner_id(uid, chat_id)
    if not partner_id:
        await message.answer("❌ Семейный кошелёк доступен только для пар в браке.")
        return

    my_bal      = await get_family_wallet(chat_id, uid)
    partner_bal = await get_family_wallet(chat_id, partner_id)
    partner     = await get_user(partner_id)
    partner_name = html.escape(partner["full_name"]) if partner else str(partner_id)
    total = my_bal + partner_bal

    await message.answer(
        f"👨‍👩‍👧 <b>Семейный кошелёк</b>\n\n"
        f"Твоя часть: <b>{my_bal} 🪙</b>\n"
        f"Часть {user_mention(partner_id, partner_name)}: <b>{partner_bal} 🪙</b>\n"
        f"━━━━━━━━━━━\n"
        f"Всего в кошельке: <b>{total} 🪙</b>\n\n"
        f"Пополнить: <code>бот пополнить семью N</code>\n"
        f"Снять: <code>бот снять семью N</code>",
        parse_mode="HTML",
    )


@router.message(BotCommand("пополнить семью", "семья пополнить", "пополнить кошелёк семьи"))
async def cmd_family_deposit(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    partner_id = await _get_partner_id(uid, chat_id)
    if not partner_id:
        await message.answer("❌ Семейный кошелёк доступен только для пар в браке.")
        return

    arg = (cmd_args or "").strip()
    if not arg.isdigit() or int(arg) <= 0:
        await message.answer("❌ Укажи сумму.\nПример: <code>бот пополнить семью 100</code>", parse_mode="HTML")
        return

    amount = int(arg)
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    if bal < amount:
        await message.answer(f"❌ Недостаточно Моры. У тебя: <b>{bal} 🪙</b>", parse_mode="HTML")
        return

    _, new_personal = await deduct_mora(uid, chat_id, amount)
    new_family = await add_to_family_wallet(chat_id, uid, amount)
    await message.answer(
        f"✅ Переведено <b>{amount} 🪙</b> в семейный кошелёк.\n"
        f"Личный баланс: <b>{new_personal} 🪙</b>\n"
        f"В семейном кошельке: <b>{new_family} 🪙</b>",
        parse_mode="HTML",
    )


@router.message(BotCommand("снять семью", "семья снять", "снять кошелёк семьи"))
async def cmd_family_withdraw(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    partner_id = await _get_partner_id(uid, chat_id)
    if not partner_id:
        await message.answer("❌ Семейный кошелёк доступен только для пар в браке.")
        return

    arg = (cmd_args or "").strip()
    if not arg.isdigit() or int(arg) <= 0:
        await message.answer("❌ Укажи сумму.\nПример: <code>бот снять семью 100</code>", parse_mode="HTML")
        return

    amount = int(arg)
    family_bal = await get_family_wallet(chat_id, uid)
    if family_bal < amount:
        await message.answer(f"❌ В твоей части кошелька только <b>{family_bal} 🪙</b>", parse_mode="HTML")
        return

    new_family = await add_to_family_wallet(chat_id, uid, -amount)
    new_personal = await add_mora(uid, chat_id, amount)
    await message.answer(
        f"✅ Снято <b>{amount} 🪙</b> из семейного кошелька.\n"
        f"Личный баланс: <b>{new_personal} 🪙</b>\n"
        f"В семейном кошельке: <b>{new_family} 🪙</b>",
        parse_mode="HTML",
    )


# ─── Анонимное сообщение в чат администрации ──────────────────────────────────


@router.message(BotCommand("анонимка", "анонимное сообщение", "аноним"))
async def cmd_anon_message(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    text = (cmd_args or "").strip()

    if not text:
        await message.answer(
            f"📨 <b>Анонимное сообщение администрации</b>\n\n"
            f"Стоимость: <b>{ANON_MSG_PRICE} 🪙</b>\n\n"
            f"Использование: <code>бот анонимка [текст]</code>\n"
            f"<i>Твоё имя не будет раскрыто администраторам.</i>",
            parse_mode="HTML",
        )
        return

    if len(text) > 1000:
        await message.answer("❌ Сообщение слишком длинное (макс. 1000 символов).")
        return

    admin_groups = get_admin_group_ids()
    if not admin_groups:
        await message.answer("❌ Администраторские группы не настроены. Обратись к владельцу.")
        return

    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    if bal < ANON_MSG_PRICE:
        await message.answer(
            f"❌ Для отправки анонимки нужно <b>{ANON_MSG_PRICE} 🪙</b>.\n"
            f"У тебя: <b>{bal} 🪙</b>.",
            parse_mode="HTML",
        )
        return

    ok, _ = await deduct_mora(uid, chat_id, ANON_MSG_PRICE)
    if not ok:
        await message.answer("❌ Не удалось списать Мору. Попробуй ещё раз.")
        return

    from aiogram import Bot
    bot: Bot = message.bot
    sent_count = 0
    
    # Create inline keyboard with "Forward to main chat" button
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📢 В основной чат", 
            callback_data=f"anon_forward:{chat_id}"
        )]
    ])
    
    for ag_id in admin_groups:
        try:
            await bot.send_message(
                ag_id,
                f"📨 <b>Анонимное сообщение</b>\n"
                f"💬 Чат: {html.escape(message.chat.title or str(chat_id))}\n\n"
                f"{html.escape(text)}",
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            sent_count += 1
        except Exception:
            pass

    if sent_count:
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer(
            f"✅ Анонимное сообщение отправлено администрации. (<b>{ANON_MSG_PRICE} 🪙</b> списано)",
            parse_mode="HTML",
        )
    else:
        # Вернём деньги, если не смогли отправить
        await add_mora(uid, chat_id, ANON_MSG_PRICE)
        await message.answer("❌ Не удалось отправить сообщение. Деньги возвращены.")


# ─── Callback: переслать анонимное сообщение в основной чат ───────────────────

@router.callback_query(F.data.startswith("anon_forward:"))
async def cb_anon_forward_to_main_chat(callback: CallbackQuery):
    """Forward anonymous message to main chat."""
    from database.db import get_channel_type, get_user_stats
    from utils.ranks import rank_level
    
    caller_id = callback.from_user.id
    admin_chat_id = callback.message.chat.id
    
    # Check if caller has admin rights
    caller_stats = await get_user_stats(caller_id, admin_chat_id)
    if not caller_stats or rank_level(caller_stats["rank"]) < rank_level("moderator"):
        await callback.answer("❌ Недостаточно прав.", show_alert=True)
        return
    
    # Extract original chat_id from callback data
    original_chat_id = int(callback.data.split(":", 1)[1])
    
    # Get main chat ID
    main_chat_id = await get_channel_type("main")
    if not main_chat_id:
        await callback.answer("❌ Основной чат не настроен.", show_alert=True)
        return
    
    # Extract anonymous message text from current message
    current_text = callback.message.text or callback.message.caption or ""
    if "📨 Анонимное сообщение" not in current_text:
        await callback.answer("❌ Не удалось получить текст сообщения.", show_alert=True)
        return
    
    # Extract just the anonymous message content (after the header)
    try:
        lines = current_text.split("\n")
        # Skip "📨 Анонимное сообщение", "💬 Чат: ...", and empty line
        anon_text = "\n".join(lines[3:]) if len(lines) > 3 else ""
    except Exception:
        await callback.answer("❌ Ошибка обработки текста.", show_alert=True)
        return
    
    if not anon_text.strip():
        await callback.answer("❌ Пустое сообщение.", show_alert=True)
        return
    
    try:
        # Send to main chat
        await callback.bot.send_message(
            main_chat_id,
            f"📣 <b>Сообщение от администрации</b>\n\n{html.escape(anon_text.strip())}",
            parse_mode="HTML",
        )
        
        # Update the admin message to show it was forwarded
        caller_name = callback.from_user.first_name or str(caller_id)
        try:
            await callback.message.edit_text(
                current_text + f"\n\n✅ <i>Переслано в основной чат администратором {html.escape(caller_name)}</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass  # Ignore if can't edit (message too old, etc.)
            
        await callback.answer("✅ Сообщение переслано в основной чат!")
        
    except Exception as e:
        await callback.answer(f"❌ Ошибка отправки: {str(e)[:50]}", show_alert=True)

