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
from datetime import datetime, timedelta, timezone

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
    buy_shop_item,
    get_admin_group_ids,
    get_family_wallet,
    get_mora,
    get_top_frame,
    get_user,
    get_user_owned_frames,
    get_vip,
    get_xp_boost_active,
    set_mora_public,
    set_top_frame,
    set_vip,
    set_xp_boost,
    get_marriage,
    get_total_family_balance,
    deduct_family_pool,
    log_family_transaction,
)
from config import (
    ANON_MSG_PRICE,
    MINI_APP_TG_URL,
    SECRET_MSG_PRICE,
    VIP_PRICE,
)
from filters.bot_command import BotCommand
from filters.rank_filter import RankFilter
from utils.helpers import resolve_target, user_mention
from utils.ranks import rank_level

router = Router()


# ─── Утилита списания из личного/семейного кошелька ───────────────────────────

async def deduct_wallet(uid: int, chat_id: int, amount: int, wallet: str) -> tuple[bool, int]:
    """Списать amount из указанного кошелька.
    wallet: 'personal' | 'family'.
    Возвращает (ok, new_balance).

    Thin wrapper around economy_service.process_payment for backward compatibility.
    """
    from services.economy_service import process_payment
    from services.exceptions import NotEnoughMoraError, NotMarriedError
    try:
        new_bal = await process_payment(uid, chat_id, amount, wallet_type=wallet)
        return True, new_bal
    except (NotEnoughMoraError, NotMarriedError) as e:
        # Return current balance on failure
        have = getattr(e, "have", 0)
        return False, have


# ─── Рамки профиля в топе ─────────────────────────────────────────────────────
#  (ключ, emoji, название, цена в Море, описание)
TOP_FRAMES: list[tuple[str, str, str, int, str]] = [
    ("default",   "🔰", "Стандарт",      0,    "Базовая рамка (бесплатно)"),
    ("warrior",   "⚔️", "Воин",           250,  "Для тех, кто не отступает"),
    ("king",      "👑", "Король",         500,  "Только для избранных"),
    ("moon",      "🌙", "Ночной",         400,  "Загадочная ночная рамка"),
    ("fire",      "🔥", "Огненный",       350,  "Яркая и горячая"),
    ("diamond",   "💎", "Алмазный",       600,  "Премиальная рамка для VIP"),
    ("star",      "⭐", "Звёздный",       300,  "Рамка победителей"),
    ("sakura",    "🌸", "Сакура",         1200, "Нежная весенняя рамка"),
    ("abyss",     "🌀", "Бездна",         1500, "Рамка из тёмных глубин"),
    ("fatui",     "⚡", "Предвестник",    1800, "Рамка вестника бури"),
    ("angel",     "🕊️", "Крылья ветра",   2200, "Лёгкая небесная рамка"),
    ("champion",  "🏆", "Чемпион",        2800, "Рамка истинного чемпиона"),
    ("celestia",  "🏰", "Целестия",       3500, "Рамка небесного замка"),
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

def _mora_text(balance: int, total: int, streak: int, display_name: str, vip: int = 0, boost: bool = False, frame: str | None = None) -> str:
    streak_line = f"\n🔥 Стрик: <b>{streak} дн.</b>" if streak > 0 else ""
    vip_line = "\n💎 <b>VIP статус активен</b>" if vip else ""
    boost_line = "\n⚡ <b>Буст XP x2 активен</b>" if boost else ""
    frame_label = _FRAME_MAP.get(frame, ("", "", frame or "—"))[2] if frame else "—"
    frame_emoji_str = _frame_emoji(frame)
    return (
        f"💰 <b>Баланс</b>{vip_line}: {display_name}\n\n"
        f"Мора: <b>{balance} 🪙</b>\n"
        f"Всего заработано: {total} 🪙"
        f"{streak_line}\n"
        f"🖼 Рамка: {frame_emoji_str} {frame_label}"
        f"{boost_line}"
    )


def _mora_keyboard(uid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Закрыть", callback_data=f"mora_close:{uid}"),
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

        # Приватность: чужой баланс можно смотреть только admin_senior+
        from database.db import get_user_stats
        from utils.ranks import is_developer
        caller_id = message.from_user.id
        if uid != caller_id and not is_developer(caller_id):
            caller_stats = await get_user_stats(caller_id, chat_id)
            caller_rank = caller_stats["rank"] if caller_stats else "user"
            if rank_level(caller_rank) < rank_level("admin_senior"):
                await message.answer("🔒 Баланс других участников могут смотреть только Старшие Администраторы и выше.")
                return

        mora = await get_mora(uid, chat_id)
        balance = (mora["balance"] or 0) if mora else 0
        total   = (mora["total_earned"] or 0) if mora else 0
        user    = await get_user(uid)
        uname   = f" (@{user['username']})" if user and user.get("username") else ""
        display = html.escape(user["full_name"]) if user else html.escape(name)
        vip_badge = " 💎" if mora and (mora["vip"] or 0) else ""
        frame   = mora["top_frame"] if mora else None
        frame_label = _FRAME_MAP.get(frame, ("", "", frame or "—"))[2] if frame else "—"
        frame_emoji_str = _frame_emoji(frame)
        await message.answer(
            f"💰 <b>Баланс</b>{vip_badge}: {user_mention(uid, display)}{uname}\n\n"
            f"Мора: <b>{balance} 🪙</b>\n"
            f"Всего заработано: {total} 🪙\n"
            f"🖼 Рамка: {frame_emoji_str} {frame_label}",
            parse_mode="HTML",
        )
        return

    # PHASE 3: own balance → Mini App in public groups
    abs_cid = abs(message.chat.id)
    btn = InlineKeyboardButton(
        text="💰 Мой баланс в Mini App",
        url=f"{MINI_APP_TG_URL}$1startapp={abs_cid}_profile",
    )
    await message.answer(
        "🔒 <b>Баланс скрыт в общих чатах — открой Mini App:</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[btn]]),
    )


@router.callback_query(F.data.startswith("mora_close:"))
async def cb_mora_close(callback: CallbackQuery):
    uid = int(callback.data.split(":")[1])
    if callback.from_user.id != uid:
        await callback.answer("🚫 Это не твоё меню!", show_alert=True)
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.answer()


# Обратная совместимость: старые кнопки mora_pub больше не используются
@router.callback_query(F.data.startswith("mora_pub:"))
async def cb_mora_public_legacy(callback: CallbackQuery):
    await callback.answer("ℹ️ Настройка приватности удалена. Баланс теперь всегда скрыт.", show_alert=True)


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
    personal_bal = mora["balance"] if mora else 0

    marriage = await get_marriage(uid, chat_id)
    buttons = []
    if marriage:
        family_bal = await get_family_wallet(chat_id, uid)
        buttons.append([
            InlineKeyboardButton(
                text=f"💰 Личный ({personal_bal} 🪙)",
                callback_data=f"buy_vip:{uid}:personal",
            ),
            InlineKeyboardButton(
                text=f"👨‍👩‍👧 Семейный ({family_bal} 🪙)",
                callback_data=f"buy_vip:{uid}:family",
            ),
        ])
    else:
        if personal_bal < VIP_PRICE:
            await message.answer(
                f"💎 <b>VIP статус</b> стоит <b>{VIP_PRICE} Моры</b>.\n\n"
                f"У тебя: <b>{personal_bal} 🪙</b> — недостаточно.\n"
                f"Зарабатывай Мору, общаясь в чате!",
                parse_mode="HTML",
            )
            return
        buttons.append([
            InlineKeyboardButton(text=f"✅ Купить за {VIP_PRICE} Моры", callback_data=f"buy_vip:{uid}:personal"),
            InlineKeyboardButton(text="❌ Отмена", callback_data=f"buy_cancel:{uid}"),
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        f"💎 <b>VIP Статус</b>\n\n"
        f"Стоимость: <b>{VIP_PRICE} 🪙</b>\n"
        f"💰 Личный: <b>{personal_bal} 🪙</b>\n\n"
        f"Что даёт VIP:\n"
        f"  💎 Золотой значок рядом с именем (профиль + таблица лидеров)\n"
        f"  📅 +15% к ежедневному чекину\n"
        f"  🎰 Скидка на гача-крутки: ×1 = 70🪙, ×10 = 650🪙\n"
        f"  🖼 Разблокирует рамку «💎 Алмазный» в магазине\n"
        f"  🏆 Питомец подсвечен цветом в Зале Славы",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("buy_vip:"))
async def cb_buy_vip(callback: CallbackQuery):
    parts = callback.data.split(":")
    uid = int(parts[1])
    wallet = parts[2] if len(parts) > 2 else "personal"

    if callback.from_user.id != uid:
        await callback.answer("🚫 Это не твоя кнопка!", show_alert=True)
        return

    chat_id = callback.message.chat.id

    if await get_vip(uid, chat_id):
        await callback.answer("💎 У тебя уже есть VIP!", show_alert=True)
        return

    ok, new_bal = await deduct_wallet(uid, chat_id, VIP_PRICE, wallet)
    if not ok:
        await callback.answer(f"❌ Недостаточно Моры! ({new_bal} / {VIP_PRICE})", show_alert=True)
        return

    await set_vip(uid, chat_id, 1)
    wallet_label = "семейного" if wallet == "family" else "личного"
    try:
        await callback.message.edit_text(
            f"💎 <b>VIP получен!</b>\n\n"
            f"Списано из {wallet_label} кошелька.\n"
            f"Баланс: <b>{new_bal} 🪙</b>\n\n"
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
    personal_bal = mora["balance"] if mora else 0

    marriage = await get_marriage(uid, chat_id)
    rows = []
    if marriage:
        family_bal = await get_family_wallet(chat_id, uid)
        for key, hours, price, label in XP_BOOST_OPTIONS:
            rows.append([
                InlineKeyboardButton(
                    text=f"💰 {label} — {price} 🪙",
                    callback_data=f"boost_buy:{uid}:{key}:personal",
                ),
                InlineKeyboardButton(
                    text=f"👨‍👩‍👧 {label}",
                    callback_data=f"boost_buy:{uid}:{key}:family",
                ),
            ])
        bal_info = f"💰 Личный: <b>{personal_bal} 🪙</b> | 👨‍👩‍👧 Семейный: <b>{family_bal} 🪙</b>"
    else:
        for key, hours, price, label in XP_BOOST_OPTIONS:
            rows.append([InlineKeyboardButton(
                text=f"⚡ {label} — {price} 🪙",
                callback_data=f"boost_buy:{uid}:{key}:personal",
            )])
        bal_info = f"Твой баланс: <b>{personal_bal} 🪙</b>"

    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"buy_cancel:{uid}")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)

    await message.answer(
        f"⚡ <b>Буст XP x2</b>\n\n"
        f"Делает все начисления XP вдвое больше на выбранное время.\n"
        f"{bal_info}\n\n"
        f"Выбери продолжительность:",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("boost_buy:"))
async def cb_boost_buy(callback: CallbackQuery):
    parts = callback.data.split(":")
    uid = int(parts[1])
    key = parts[2]
    wallet = parts[3] if len(parts) > 3 else "personal"

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

    ok, new_bal = await deduct_wallet(uid, chat_id, price, wallet)
    if not ok:
        await callback.answer(f"❌ Недостаточно Моры! ({new_bal} / {price})", show_alert=True)
        return

    until = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    await set_xp_boost(uid, chat_id, until)
    wallet_label = "семейного" if wallet == "family" else "личного"
    try:
        await callback.message.edit_text(
            f"⚡ <b>Буст XP x2 активирован!</b>\n\n"
            f"Продолжительность: <b>{label}</b>\n"
            f"Списано из {wallet_label} кошелька.\n"
            f"Баланс: <b>{new_bal} 🪙</b>",
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
    owned = await get_user_owned_frames(uid, chat_id)

    lines = ["🖼 <b>Рамки профиля в топе</b>\n"]
    for key, emoji, name, price, desc in TOP_FRAMES:
        active = " ◀ активна" if key == current_frame else ""
        if price == 0 or key in owned:
            status = "✅ в коллекции"
        else:
            status = f"💳 {price} 🪙"
        lines.append(f"{emoji} <b>{name}</b> — {status}{active}\n  <i>{desc}</i>")

    lines.append(f"\n💰 Баланс: <b>{bal} 🪙</b>")
    lines.append("\n<code>бот купить рамку</code> — выбрать / сменить")
    await message.answer("\n".join(lines), parse_mode="HTML")


_FRAME_PAGE_SIZE = 4


def _frame_keyboard(uid: int, current_frame: str | None, owned: list, page: int) -> InlineKeyboardMarkup:
    """Build a paginated frame selection keyboard."""
    total = len(TOP_FRAMES)
    pages = (total + _FRAME_PAGE_SIZE - 1) // _FRAME_PAGE_SIZE
    page = max(0, min(page, pages - 1))
    start = page * _FRAME_PAGE_SIZE
    slice_ = TOP_FRAMES[start: start + _FRAME_PAGE_SIZE]

    rows = []
    for key, emoji, name, price, _ in slice_:
        if key == current_frame:
            label = f"· {emoji} {name} · (активна)"
        elif price == 0 or key in owned:
            label = f"✅ {emoji} {name} — Надеть"
        else:
            label = f"💳 {emoji} {name} — {price} 🪙"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"frame_buy:{uid}:{key}")])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀", callback_data=f"frame_page:{uid}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="▶", callback_data=f"frame_page:{uid}:{page + 1}"))
    if len(nav) > 1 or pages > 1:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"buy_cancel:{uid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(BotCommand("купить рамку", "рамку", "купить frame"))
async def cmd_buy_frame(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    current_frame = mora["top_frame"] if mora else None
    owned = await get_user_owned_frames(uid, chat_id)

    arg = (cmd_args or "").strip().lower()

    if not arg:
        await message.answer(
            f"🖼 <b>Выбери рамку</b>\n\nТвой баланс: <b>{bal} 🪙</b>",
            parse_mode="HTML",
            reply_markup=_frame_keyboard(uid, current_frame, owned, 0),
        )
        return

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
    if key == current_frame:
        await message.answer(f"{emoji} Рамка «{name}» уже активна!")
        return
    if price == 0 or key in owned:
        btn_text = f"✅ Надеть «{name}»"
    else:
        btn_text = f"💳 Купить за {price} 🪙"
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=btn_text, callback_data=f"frame_buy:{uid}:{key}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"buy_cancel:{uid}"),
    ]])
    await message.answer(
        f"{emoji} <b>{name}</b>\n{desc}\n\nЦена: {'бесплатно' if price == 0 or key in owned else f'{price} 🪙'}\nТвой баланс: {bal} 🪙",
        parse_mode="HTML",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("frame_page:"))
async def cb_frame_page(callback: CallbackQuery):
    parts = callback.data.split(":")
    uid = int(parts[1])
    page = int(parts[2])
    if callback.from_user.id != uid:
        await callback.answer("🚫 Это не твоя кнопка!", show_alert=True)
        return
    chat_id = callback.message.chat.id
    mora = await get_mora(uid, chat_id)
    current_frame = mora["top_frame"] if mora else None
    owned = await get_user_owned_frames(uid, chat_id)
    bal = mora["balance"] if mora else 0
    try:
        await callback.message.edit_reply_markup(
            reply_markup=_frame_keyboard(uid, current_frame, owned, page)
        )
    except Exception:
        pass
    await callback.answer()


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

    owned = await get_user_owned_frames(uid, chat_id)
    new_bal = mora["balance"] if mora else 0

    if price > 0 and fkey not in owned:
        # Пробуем списать из личного кошелька
        ok, new_bal = await deduct_wallet(uid, chat_id, price, "personal")
        if not ok:
            # Пробуем семейный
            marriage = await get_marriage(uid, chat_id)
            if marriage:
                ok, new_bal = await deduct_wallet(uid, chat_id, price, "family")
            if not ok:
                await callback.answer(f"❌ Недостаточно Моры! ({new_bal} / {price})", show_alert=True)
                return
        await buy_shop_item(uid, chat_id, "frame", fkey)

    await set_top_frame(uid, chat_id, fkey)
    try:
        await callback.message.edit_text(
            f"{emoji} <b>Рамка «{fname}» активирована!</b>\n\n"
            f"Теперь она будет отображаться в топе чата.\n"
            f"💰 Баланс: <b>{new_bal} 🪙</b>",
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

    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE users SET balance=balance-$1 WHERE user_id=$2 AND COALESCE(balance,0)>=$3",
            (amount, uid, amount),
        )
        if cursor.rowcount == 0:
            await message.answer("❌ Не удалось списать Мору. Попробуй ещё раз.")
            return
        await db.commit()
        async with db.execute(
            "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=$1",
            (uid,),
        ) as c:
            row = await c.fetchone()
        new_personal = row[0] if row else 0
    new_family = await add_to_family_wallet(chat_id, uid, amount)
    await log_family_transaction(chat_id, uid, "deposit", amount, "Пополнение через бот")
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
    total_bal, my_bal, _ = await get_total_family_balance(chat_id, uid)
    if total_bal < amount:
        await message.answer(
            f"❌ В семейном кошельке только <b>{total_bal} 🪙</b>\n"
            f"  (твой вклад: {my_bal} 🪙, вклад партнёра: {total_bal - my_bal} 🪙)",
            parse_mode="HTML",
        )
        return

    new_total = await deduct_family_pool(chat_id, uid, partner_id, amount)
    if new_total < 0:
        # Гонка условий — откат (крайне маловероятно)
        await message.answer("❌ Недостаточно средств в семейном кошельке.")
        return
    await log_family_transaction(chat_id, uid, "withdraw", amount, "Снятие через бот")
    new_personal = await add_mora(uid, chat_id, amount)
    await message.answer(
        f"✅ Снято <b>{amount} 🪙</b> из семейного кошелька.\n"
        f"Личный баланс: <b>{new_personal} 🪙</b>\n"
        f"В семейном кошельке: <b>{new_total} 🪙</b>",
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

    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE users SET balance=balance-$1 WHERE user_id=$2 AND COALESCE(balance,0)>=$3",
            (ANON_MSG_PRICE, uid, ANON_MSG_PRICE),
        )
        if cursor.rowcount == 0:
            await message.answer("❌ Не удалось списать Мору. Попробуй ещё раз.")
            return
        await db.commit()

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
        # Send to main chat as anonymous user message  
        await callback.bot.send_message(
            main_chat_id,
            f"📨 <b>Анонимное сообщение</b>\n\n{html.escape(anon_text.strip())}",
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


# ─── Секретные сообщения ─────────────────────────────────────────────────────

@router.message(BotCommand("секрет", "приват", "secret"))
async def cmd_secret_message(message: Message, cmd_args: str):
    """Send a secret message that only recipient can read."""
    
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда работает только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    
    # Parse target and message text
    parts = (cmd_args or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            f"📨 <b>Секретное сообщение</b>\n\n"
            f"Стоимость: <b>{SECRET_MSG_PRICE} 🪙</b>\n\n" 
            f"Использование: <code>бот секрет @user текст</code>\n"
            f"<i>Только получатель сможет прочитать сообщение.</i>",
            parse_mode="HTML",
        )
        return
        
    target_str, secret_text = parts
    
    # Resolve target user
    target_uid, target_name, _ = await resolve_target(message, target_str)
    if target_uid is None:
        await message.answer("❌ Пользователь не найден.")
        return
        
    if target_uid == uid:
        await message.answer("❌ Нельзя отправить секретное сообщение самому себе.")
        return
        
    if len(secret_text) > 30:
        await message.answer("❌ Секретное сообщение слишком длинное (макс. 30 символов).")
        return

    # Check balance
    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    if bal < SECRET_MSG_PRICE:
        await message.answer(
            f"❌ Для отправки секретного сообщения нужно <b>{SECRET_MSG_PRICE} 🪙</b>.\n"
            f"У тебя: <b>{bal} 🪙</b>.",
            parse_mode="HTML",
        )
        return

    # Deduct mora
    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE users SET balance=balance-$1 WHERE user_id=$2 AND COALESCE(balance,0)>=$3",
            (SECRET_MSG_PRICE, uid, SECRET_MSG_PRICE),
        )
        if cursor.rowcount == 0:
            await message.answer("❌ Не удалось списать Мору. Попробуй ещё раз.")
            return
        await db.commit()
        
    # Create short unique ID for secret message
    import hashlib
    import time
    secret_id = hashlib.md5(f"{uid}:{target_uid}:{time.time()}:{secret_text}".encode()).hexdigest()[:8]
    
    # Store secret text temporarily in database 
    # For now, use base64 encoding in callback (limited to ~40 chars of original text)
    import base64
    # Truncate text to fit in callback_data limit (64 bytes total)
    text_for_callback = secret_text[:30]  # Conservative limit
    encoded_text = base64.b64encode(text_for_callback.encode()).decode()
    
    # Create callback data: secret:target_uid:sender_uid:encoded_text
    callback_data = f"secret:{target_uid}:{uid}:{encoded_text}"
    
    # Create button for recipient
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔐 Прочитать секретное сообщение",
            callback_data=callback_data
        )]
    ])
    
    sender_name = message.from_user.first_name or str(uid)
    
    try:
        # Delete original command
        await message.delete()
    except Exception:
        pass
    
    # Send secret message prompt
    await message.answer(
        f"📨 <b>Секретное сообщение</b>\n"
        f"От: {html.escape(sender_name)}\n"
        f"Для: {html.escape(target_name)}\n\n"
        f"🔐 <i>Только получатель может прочитать содержимое.</i>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("secret:"))
async def cb_read_secret_message(callback: CallbackQuery):
    """Handle reading secret messages."""
    caller_id = callback.from_user.id
    
    try:
        # Parse callback data: secret:target_uid:sender_uid:encoded_text
        parts = callback.data.split(":", 3)
        if len(parts) != 4:
            await callback.answer("❌ Ошибка данных.", show_alert=True)
            return
            
        _, target_uid_str, sender_uid_str, encoded_text = parts
        target_uid = int(target_uid_str)
        sender_uid = int(sender_uid_str)
        
        # Check if caller is the intended recipient
        if caller_id != target_uid:
            await callback.answer("🔐 Это сообщение не для тебя!", show_alert=True)
            return
            
        # Decode message
        import base64
        try:
            secret_text = base64.b64decode(encoded_text.encode()).decode()
        except Exception:
            await callback.answer("❌ Не удалось расшифровать сообщение.", show_alert=True)
            return
            
        # Get sender info
        sender_user = await get_user(sender_uid)
        sender_name = sender_user["full_name"] if sender_user else str(sender_uid)
        
        # Show secret message in alert popup (private)
        await callback.answer(
            f"🔐 Секретное сообщение от {sender_name}:\n\n{secret_text}",
            show_alert=True
        )
        
    except (ValueError, IndexError) as e:
        await callback.answer("❌ Некорректные данные.", show_alert=True)

