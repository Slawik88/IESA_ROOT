"""
🛠 Панель разработчика — команды для DEVELOPER_ID и высших рангов.

Команды:
  бот эвент [сундук|дилижанс]          — принудительно запустить ивент во всех активных чатах
  бот сетбаланс [сумма] [@user]         — установить/прибавить мору пользователю
  бот казна                             — показать баланс казны в текущем чате
  бот казна дать [@user] [сумма]        — выдать мору из казны игроку (owner+)
  бот казна забрать [@user] [сумма]     — забрать мору у игрока в казну (owner+)
  бот датьпредмет [key] [@user]         — выдать предмет из каталога
  бот чистка настройка [параметры]      — настройка чистки чата (owner+)
"""

import html
import logging

from aiogram import Router
from aiogram.types import Message

from config import DEVELOPER_ID
from database.db import (
    add_mora,
    add_to_treasury,
    get_all_active_chats,
    get_mora,
    get_treasury,
    get_user,
    set_mora_balance,
    add_gacha_item,
    get_user_stats,
)
from filters.bot_command import BotCommand
from utils.helpers import resolve_target, user_mention
from utils.ranks import is_developer

router = Router()
log = logging.getLogger(__name__)


def _dev_only(uid: int) -> bool:
    return is_developer(uid)


async def _log_to_dev(bot, text: str):
    """Отправить лог-сообщение разработчику в личку."""
    try:
        if DEVELOPER_ID:
            await bot.send_message(DEVELOPER_ID, f"🛠 <b>[DEV LOG]</b>\n{text}", parse_mode="HTML")
    except Exception as e:
        log.warning("Dev log DM failed: %s", e)


# ─── бот эвент [тип] ──────────────────────────────────────────────────────────

@router.message(BotCommand("эвент", "event", "dev_event"))
async def cmd_dev_event(message: Message, cmd_args: str):
    if not _dev_only(message.from_user.id):
        return  # молчим для не-разработчиков

    event_type = (cmd_args or "").strip().lower()
    chat_id = message.chat.id
    bot = message.bot

    if event_type in ("сундук", "chest"):
        from handlers.tax_event import launch_chest_event
        event_id = await launch_chest_event(bot, chat_id)
        result = f"✅ Сундук запущен в чате {chat_id} (event_id={event_id})" if event_id else "❌ Не удалось запустить сундук"
        await message.answer(result)
        await _log_to_dev(bot, f"бот эвент сундук → chat {chat_id}\n{result}")

    elif event_type in ("дилижанс", "diligence"):
        from handlers.diligence import _launch_diligence
        ok = await _launch_diligence(bot, chat_id)
        result = f"✅ Дилижанс запущен в чате {chat_id}" if ok else "⚠️ Дилижанс уже активен"
        await message.answer(result)
        await _log_to_dev(bot, f"бот эвент дилижанс → chat {chat_id}\n{result}")

    else:
        await message.answer(
            "🛠 <b>Dev: Запуск ивента</b>\n\n"
            "Использование: <code>бот эвент [тип]</code>\n\n"
            "Типы:\n"
            "  <code>сундук</code>     — Богатый сундук\n"
            "  <code>дилижанс</code>   — Дилижанс (кликер)",
            parse_mode="HTML",
        )


# ─── бот сетбаланс [сумма] [@user] ───────────────────────────────────────────

@router.message(BotCommand("сетбаланс", "setbalance", "setbal"))
async def cmd_dev_setbalance(message: Message, cmd_args: str):
    if not _dev_only(message.from_user.id):
        return

    parts = (cmd_args or "").strip().split()
    chat_id = message.chat.id

    # Парсим: [сумма] или [@user сумма] или [сумма @user]
    target_id: int | None = None
    amount: int | None = None
    action = "set"  # "set" или "add" (если со знаком)

    args_clean = cmd_args or ""
    target_id, target_name, rest = await resolve_target(message, args_clean)
    if target_id is None:
        target_id = message.from_user.id
        target_name = message.from_user.full_name
        rest = args_clean

    amount_str = (rest or "").strip().lstrip("+")
    if amount_str.lstrip("-").isdigit():
        amount = int(amount_str)
        action = "add" if (rest or "").strip().startswith("+") else "set"
    else:
        await message.answer(
            "🛠 <b>Dev: Сетбаланс</b>\n\n"
            "Использование:\n"
            "  <code>бот сетбаланс 1000</code> — установить свой баланс\n"
            "  <code>бот сетбаланс 1000 @user</code> — установить баланс @user\n"
            "  <code>бот сетбаланс +500 @user</code> — добавить к балансу",
            parse_mode="HTML",
        )
        return

    current = await get_mora(target_id, chat_id)
    old_bal = current["balance"] if current else 0

    if action == "set":
        await set_mora_balance(target_id, chat_id, amount)
        new_bal = amount
        op_text = f"установлен в {amount}"
    else:
        new_bal = await add_mora(target_id, chat_id, amount)
        op_text = f"изменён на {'+'if amount>=0 else ''}{amount} (итого {new_bal})"

    result = (
        f"✅ Баланс {html.escape(str(target_name))} ({target_id}): "
        f"{old_bal} → <b>{new_bal} 🪙</b>"
    )
    await message.answer(result, parse_mode="HTML")
    await _log_to_dev(
        message.bot,
        f"бот сетбаланс: uid={target_id} ({target_name}), {op_text}\n"
        f"Исполнитель: {message.from_user.id} в chat {chat_id}",
    )


# ─── бот казна ────────────────────────────────────────────────────────────────

@router.message(BotCommand("казна", "treasury"))
async def cmd_treasury(message: Message):
    """Показать баланс казны. Доступно admin_senior+."""
    from filters.rank_filter import RankFilter
    from database.db import get_user_stats as _gs
    from utils.ranks import rank_level as _rl

    uid = message.from_user.id
    chat_id = message.chat.id

    # Проверка ранга (admin_senior+ или developer)
    if not _dev_only(uid):
        stats = await _gs(uid, chat_id)
        rank = stats["rank"] if stats else "user"
        if _rl(rank) < _rl("admin_senior"):
            await message.answer("🔒 Только Старшие Администраторы и выше могут смотреть казну.")
            return

    balance = await get_treasury(chat_id)
    await message.answer(
        f"🏦 <b>Казна чата</b>\n\n"
        f"💰 Баланс: <b>{balance} 🪙</b>\n\n"
        f"<i>Пополняется из налогов (НДС):\n"
        f"• 3–8% с переводов\n"
        f"• 5% с выигрышей в казино\n"
        f"• 5% с покупок в гаче\n"
        f"• 5% с покупок в магазине\n"
        f"• 5% с покупки чат-бафа\n"
        f"• 10% с покупки лотерейных билетов\n"
        f"• 10% с процентов по вкладам\n"
        f"• 6.5–7% с экспедиций\n"
        f"• 10–40% с прибыли по облигациям\n"
        f"• 8% с лотереи (от 50 🪙)</i>",
        parse_mode="HTML",
    )


# ─── бот датьпредмет [key] [@user] ───────────────────────────────────────────

_DEV_ITEM_CATALOG = {
    # Legendary
    "lego_gnosis":    ("✨ Гнозис Балладеера",       "legendary"),
    "lego_scepter":   ("🏛 Скипетр Дендро Архонта",  "legendary"),
    "lego_pantalone": ("🎩 Маска Панталоне",          "legendary"),
    "lego_abyss":     ("🌀 Корона Бездны",            "legendary"),
    "lego_fatui":     ("⚡ Перст Предвестника",       "legendary"),
    # Rare
    "rare_crown":     ("👑 Серебряная корона",        "rare"),
    "rare_catalyst":  ("🔮 Магический катализатор",   "rare"),
    "rare_cape":      ("🧣 Алый плащ",                "rare"),
    "rare_gem":       ("💎 Сапфир полуночи",          "rare"),
    # Common
    "cmn_sword":      ("⚔️ Тупой клинок",            "common"),
    "cmn_bow":        ("🏹 Кривой лук",               "common"),
    "cmn_book":       ("📕 Потрёпанный дневник",       "common"),
    "cmn_ring":       ("💍 Дешёвое кольцо",           "common"),
    "cmn_shield":     ("🛡 Ржавый щит",               "common"),
    # Dev-only special
    "dev_crown":      ("👑 Корона Разработчика",       "legendary"),
}


@router.message(BotCommand("датьпредмет", "giveitem", "give_item", "выдатьпредмет"))
async def cmd_dev_give_item(message: Message, cmd_args: str):
    if not _dev_only(message.from_user.id):
        return

    args = (cmd_args or "").strip().split()
    chat_id = message.chat.id
    bot = message.bot

    if not args:
        catalog_text = "\n".join(
            f"  <code>{k}</code> — {v[0]} ({v[1]})"
            for k, v in _DEV_ITEM_CATALOG.items()
        )
        await message.answer(
            "🛠 <b>Dev: Дать предмет</b>\n\n"
            "Использование:\n"
            "  <code>бот датьпредмет [key] [@user]</code>\n\n"
            f"<b>Доступные ключи:</b>\n{catalog_text}",
            parse_mode="HTML",
        )
        return

    # Парсим: [key] или [key @user] или [@user key]
    item_key = None
    for a in args:
        if a in _DEV_ITEM_CATALOG:
            item_key = a
            break

    if not item_key:
        await message.answer(f"❌ Неизвестный предмет. Список: <code>бот датьпредмет</code>", parse_mode="HTML")
        return

    remaining = " ".join(a for a in args if a != item_key)
    target_id, target_name, _ = await resolve_target(message, remaining)
    if not target_id:
        target_id = message.from_user.id
        target_name = message.from_user.full_name

    item_name, rarity = _DEV_ITEM_CATALOG[item_key]
    await add_gacha_item(target_id, chat_id, item_key, item_name, rarity)

    result = (
        f"✅ Выдан предмет <b>{item_name}</b> ({rarity})\n"
        f"👤 Получатель: {html.escape(str(target_name))} ({target_id})"
    )
    await message.answer(result, parse_mode="HTML")
    await _log_to_dev(
        bot,
        f"бот датьпредмет: {item_key} → uid={target_id} ({target_name})\n"
        f"Исполнитель: {message.from_user.id} в chat {chat_id}",
    )


# ─── бот чистка настройка ─────────────────────────────────────────────────────

@router.message(BotCommand("чистка настройка", "cleanup config", "cleanup_config"))
async def cmd_cleanup_config(message: Message, cmd_args: str):
    """
    бот чистка настройка показать
    бот чистка настройка [дата YYYY-MM-DD HH:MM] [норма N] [предупредить Xч]
    Доступно: owner и developer только.
    """
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo
    from database.db import get_cleanup_config, set_cleanup_config, set_cleanup_reminder_sent
    from utils.ranks import rank_level as _rl

    _ZURICH = ZoneInfo("Europe/Zurich")

    uid = message.from_user.id
    chat_id = message.chat.id

    if message.chat.type == "private":
        await message.answer("❌ Команда работает только в чате.")
        return

    # owner или developer
    if not _dev_only(uid):
        stats = await get_user_stats(uid, chat_id)
        rank = stats["rank"] if stats else "user"
        if _rl(rank) < _rl("owner"):
            return  # молчим

    raw = (cmd_args or "").strip()

    # ── показать текущие настройки
    if not raw or raw.lower() in ("показать", "show"):
        cfg = await get_cleanup_config(chat_id)
        ts = cfg.get("next_cleanup_at")
        if ts:
            if hasattr(ts, "tzinfo") and ts.tzinfo:
                dt_local = ts.astimezone(_ZURICH)
            else:
                from datetime import timezone as _tz
                dt_local = _dt.fromisoformat(str(ts)).replace(tzinfo=_tz.utc).astimezone(_ZURICH)
            date_fmt = dt_local.strftime("%d.%m.%Y %H:%M (Цюрих)")
        else:
            date_fmt = "не установлена"
        norm = cfg.get("cleanup_message_norm") or 70
        warn = cfg.get("cleanup_warn_hours") or 48
        await message.answer(
            f"🧹 <b>Текущие настройки чистки:</b>\n\n"
            f"📅 Дата: <b>{date_fmt}</b>\n"
            f"📊 Норма: <b>{norm} сообщений</b>\n"
            f"🔔 Предупреждение: за <b>{warn} ч</b>\n\n"
            f"Изменить: <code>бот чистка настройка 2026-04-05 20:00 норма 70 предупредить 48</code>",
            parse_mode="HTML",
        )
        return

    # ── парсинг аргументов: выделяем дату, норму, предупреждение
    import re as _re
    new_date: str | None = None
    new_norm: int | None = None
    new_warn: int | None = None

    # норма N
    m_norm = _re.search(r'\bнорма\s+(\d+)', raw, _re.IGNORECASE)
    if m_norm:
        new_norm = int(m_norm.group(1))
        raw = raw[:m_norm.start()] + raw[m_norm.end():]

    # предупредить за Xч  / предупредить X
    m_warn = _re.search(r'\bпредупредит[ьe]\s+(\d+)', raw, _re.IGNORECASE)
    if m_warn:
        new_warn = int(m_warn.group(1))
        raw = raw[:m_warn.start()] + raw[m_warn.end():]

    # дата YYYY-MM-DD HH:MM или DD.MM.YYYY HH:MM
    raw = raw.strip()
    dt_local = None
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            dt_local = _dt.strptime(raw, fmt).replace(tzinfo=_ZURICH)
            break
        except ValueError:
            pass

    if dt_local is not None:
        if dt_local < _dt.now(_ZURICH):
            await message.answer("❌ Дата уже в прошлом. Укажи будущую дату.")
            return
        from datetime import timezone as _tz
        dt_utc = dt_local.astimezone(_tz.utc)
        new_date = dt_utc.replace(tzinfo=None).isoformat()

    if new_date is None and new_norm is None and new_warn is None:
        await message.answer(
            "❌ Не распознаны параметры.\n\n"
            "Примеры:\n"
            "<code>бот чистка настройка 2026-04-05 20:00 норма 70 предупредить 48</code>\n"
            "<code>бот чистка настройка норма 50</code>\n"
            "<code>бот чистка настройка показать</code>",
            parse_mode="HTML",
        )
        return

    await set_cleanup_config(chat_id, new_date, new_norm, new_warn)
    if new_date:
        await set_cleanup_reminder_sent(chat_id, 0)

    # подтверждение
    cfg = await get_cleanup_config(chat_id)
    ts = cfg.get("next_cleanup_at")
    if ts:
        if hasattr(ts, "tzinfo") and ts.tzinfo:
            dt_local2 = ts.astimezone(_ZURICH)
        else:
            from datetime import timezone as _tz
            dt_local2 = _dt.fromisoformat(str(ts)).replace(tzinfo=_tz.utc).astimezone(_ZURICH)
        date_fmt = dt_local2.strftime("%d.%m.%Y %H:%M (Цюрих)")
    else:
        date_fmt = "не установлена"
    norm = cfg.get("cleanup_message_norm") or 70
    warn = cfg.get("cleanup_warn_hours") or 48
    await message.answer(
        f"✅ <b>Чистка настроена:</b>\n\n"
        f"📅 Дата: <b>{date_fmt}</b>\n"
        f"📊 Норма: <b>{norm} сообщений</b>\n"
        f"🔔 Предупреждение: за <b>{warn} ч</b>",
        parse_mode="HTML",
    )


# ─── бот казна дать [@user] [сумма] ──────────────────────────────────────────

@router.message(BotCommand("казна дать", "treasury give", "казна выдать"))
async def cmd_treasury_give(message: Message, cmd_args: str):
    """Выдать мору из казны пользователю. Доступно owner+ и developer."""
    from database.db import get_user_stats as _gs
    from database.postgres import connect as postgres_connect
    from utils.ranks import rank_level as _rl

    uid = message.from_user.id
    chat_id = message.chat.id

    if message.chat.type == "private":
        await message.answer("❌ Команда работает только в чате.")
        return

    if not _dev_only(uid):
        stats = await _gs(uid, chat_id)
        rank = stats["rank"] if stats else "user"
        if _rl(rank) < _rl("owner"):
            await message.answer("🔒 Только Владелец и Разработчик могут управлять казной.")
            return

    target_id, target_name, rest = await resolve_target(message, cmd_args or "")
    if not target_id:
        await message.answer(
            "❌ Укажи пользователя и сумму.\n"
            "Пример: <code>бот казна дать @user 500</code>",
            parse_mode="HTML",
        )
        return

    amount_str = (rest or "").strip()
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await message.answer("❌ Укажи корректную сумму (> 0).")
        return
    amount = int(amount_str)

    treasury_bal = await get_treasury(chat_id)
    if treasury_bal < amount:
        await message.answer(f"❌ В казне недостаточно средств ({treasury_bal}/{amount} 🪙)")
        return

    # Atomic: deduct from treasury + credit to user
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE chat_treasury SET balance=balance-? WHERE chat_id=? AND balance>=?",
            (amount, chat_id, amount),
        )
        if cursor.rowcount == 0:
            await message.answer("❌ Не удалось списать из казны.")
            return
        await db.execute(
            """INSERT INTO treasury_log (chat_id, user_id, amount, source, created_at)
               VALUES (?,?,?,?,NOW())""",
            (chat_id, uid, -amount, "treasury_give"),
        )
        await db.commit()

    new_bal = await add_mora(target_id, chat_id, amount)
    new_treasury = await get_treasury(chat_id)

    mention = user_mention(target_id, target_name)
    admin_name = html.escape(message.from_user.full_name)
    await message.answer(
        f"✅ Из казны выдано <b>{amount} 🪙</b> → {mention}\n\n"
        f"💰 Казна: {new_treasury} 🪙\n"
        f"👤 Баланс игрока: {new_bal} 🪙\n"
        f"📝 Выдал: {admin_name}",
        parse_mode="HTML",
    )


# ─── бот казна забрать [@user] [сумма] ───────────────────────────────────────

@router.message(BotCommand("казна забрать", "treasury take", "казна собрать"))
async def cmd_treasury_take(message: Message, cmd_args: str):
    """Забрать мору у пользователя в казну. Доступно owner+ и developer."""
    from database.db import get_user_stats as _gs
    from database.postgres import connect as postgres_connect
    from utils.ranks import rank_level as _rl

    uid = message.from_user.id
    chat_id = message.chat.id

    if message.chat.type == "private":
        await message.answer("❌ Команда работает только в чате.")
        return

    if not _dev_only(uid):
        stats = await _gs(uid, chat_id)
        rank = stats["rank"] if stats else "user"
        if _rl(rank) < _rl("owner"):
            await message.answer("🔒 Только Владелец и Разработчик могут управлять казной.")
            return

    target_id, target_name, rest = await resolve_target(message, cmd_args or "")
    if not target_id:
        await message.answer(
            "❌ Укажи пользователя и сумму.\n"
            "Пример: <code>бот казна забрать @user 500</code>",
            parse_mode="HTML",
        )
        return

    amount_str = (rest or "").strip()
    if not amount_str.isdigit() or int(amount_str) <= 0:
        await message.answer("❌ Укажи корректную сумму (> 0).")
        return
    amount = int(amount_str)

    # Atomic: deduct from user
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE user_mora SET balance=balance-? WHERE user_id=? AND chat_id=? AND balance>=?",
            (amount, target_id, chat_id, amount),
        )
        if cursor.rowcount == 0:
            mora_row = await get_mora(target_id, chat_id)
            bal = mora_row["balance"] if mora_row else 0
            await message.answer(f"❌ У игрока недостаточно Моры ({bal}/{amount} 🪙)")
            return
        await db.commit()

    # Credit treasury
    new_treasury = await add_to_treasury(chat_id, amount, "treasury_take", uid)

    mora_row = await get_mora(target_id, chat_id)
    player_bal = mora_row["balance"] if mora_row else 0

    mention = user_mention(target_id, target_name)
    admin_name = html.escape(message.from_user.full_name)
    await message.answer(
        f"✅ Забрано <b>{amount} 🪙</b> у {mention} → в казну\n\n"
        f"💰 Казна: {new_treasury} 🪙\n"
        f"👤 Баланс игрока: {player_bal} 🪙\n"
        f"📝 Забрал: {admin_name}",
        parse_mode="HTML",
    )

