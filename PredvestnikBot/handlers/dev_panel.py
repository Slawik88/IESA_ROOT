"""
🛠 Панель разработчика — команды только для DEVELOPER_ID.

Команды:
  бот эвент [сундук|дилижанс]  — принудительно запустить ивент во всех активных чатах
  бот сетбаланс [сумма] [@user] — установить/прибавить мору пользователю
  бот казна                    — показать баланс казны в текущем чате
"""

import html
import logging

from aiogram import Router
from aiogram.types import Message

from config import DEVELOPER_ID
from database.db import (
    add_mora,
    get_all_active_chats,
    get_mora,
    get_treasury,
    get_user,
    set_mora_balance,
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
        f"<i>Пополняется из налогов:\n"
        f"• 0.5% с каждого перевода\n"
        f"• 1% с проигрышей в казино\n\n"
        f"Дивиденды выплачиваются каждую субботу в 18:00 (Цюрих)</i>",
        parse_mode="HTML",
    )
