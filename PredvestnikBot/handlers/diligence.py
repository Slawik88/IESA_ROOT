"""
🚚 Дилижанс — высоконагруженный групповой ивент.

Логика:
 - Запускается по пятницам в 20:00 (Europe/Zurich) через планировщик
 - Можно запустить вручную командой «бот дилижанс» (admin_senior+)
 - Участники нажимают кнопку «⚔️ Атаковать!» (лимит 30 кликов на человека)
 - Ивент заканчивается при 500 кликах ИЛИ через 10 минут
 - Награда: 2000 🪙 делится пропорционально кликам
 - Все подсчёты ТОЛЬКО in-memory до финала, потом один массовый INSERT в DB
"""

import asyncio
import logging
import time
from collections import defaultdict

from aiogram import Router
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import add_mora
from filters.bot_command import BotCommand
from filters.rank_filter import RankFilter
from services.recent_users import get_recent_user
from utils.helpers import user_mention

from filters.chat_mode import MainChatOnly
router = Router()
router.message.filter(MainChatOnly())

log = logging.getLogger(__name__)

# ─── In-memory state ─────────────────────────────────────────────────────────
_DILIGENCE_ACTIVE: dict[int, bool] = {}        # chat_id → bool
_DILIGENCE_CLICKS: dict[int, dict[int, int]] = defaultdict(dict)  # chat_id → {uid: clicks}
_DILIGENCE_MSG_ID: dict[int, int] = {}         # chat_id → telegram message_id
_DILIGENCE_START:  dict[int, float] = {}       # chat_id → unix time started

_DILIGENCE_GOAL    = 500   # clicks to finish early
_DILIGENCE_REWARD  = 2000  # total mora pool
_DILIGENCE_TIMEOUT = 600   # 10 minutes (seconds)
_CLICK_LIMIT       = 30    # max clicks per user


def _total_clicks(chat_id: int) -> int:
    return sum(_DILIGENCE_CLICKS[chat_id].values())


def _progress_bar(current: int, goal: int = _DILIGENCE_GOAL, width: int = 16) -> str:
    filled = int(width * min(current, goal) / goal)
    return "█" * filled + "░" * (width - filled)


def _event_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    clicks = _total_clicks(chat_id)
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=f"⚔️ Атаковать! [{clicks}/{_DILIGENCE_GOAL}]",
            callback_data=f"diligence:{chat_id}",
        )
    ]])


async def _finish_event(bot, chat_id: int, reason: str):
    """Финал ивента: распределить мору пропорционально кликам."""
    _DILIGENCE_ACTIVE[chat_id] = False
    participants = dict(_DILIGENCE_CLICKS[chat_id])
    total = sum(participants.values())
    _DILIGENCE_CLICKS[chat_id].clear()

    if not participants or total == 0:
        try:
            await bot.send_message(chat_id, "🚚 Дилижанс уехал без боя — никто не атаковал!")
        except Exception as _e:
            _log.debug("%s", _e)
        return

    # Если цель НЕ достигнута — участники получают лишь 10% награды
    goal_reached = total >= _DILIGENCE_GOAL
    effective_reward = _DILIGENCE_REWARD if goal_reached else round(_DILIGENCE_REWARD * 0.10)

    # Один раз пишем в БД за всех
    rewards: list[tuple[int, int]] = []
    for uid, clicks in participants.items():
        share = round(effective_reward * clicks / total)
        if share > 0:
            await add_mora(uid, chat_id, share)
            rewards.append((uid, share))
            try:
                from api.economy import log_wallet_tx
                await log_wallet_tx(uid, chat_id, "income", share, "event", "🚚 Дилижанс")
            except Exception as _e:
                _log.debug("%s", _e)

    # Топ-5 для итогового сообщения
    top = sorted(rewards, key=lambda x: x[1], reverse=True)[:5]
    status = "Дилижанс разгромлен!" if goal_reached else "Дилижанс уехал... цель не достигнута."
    lines = [f"🚚 <b>{status}</b> ({reason})\n",
             f"🏆 <b>Общий котёл: {effective_reward} 🪙</b>{'' if goal_reached else ' (штраф: цель не достигнута)'}\n",
             f"<b>Топ участников:</b>"]
    for uid, mora in top:
        _cached = get_recent_user(uid)
        _name = _cached["full_name"] if _cached else str(uid)
        lines.append(f"  ⚔️ {user_mention(uid, _name)} — <b>+{mora} 🪙</b>")
    lines.append(f"\n👥 Всего участников: {len(participants)}")

    try:
        msg_id = _DILIGENCE_MSG_ID.get(chat_id)
        if msg_id:
            await bot.edit_message_reply_markup(chat_id, msg_id, reply_markup=None)
    except Exception as _e:
        _log.debug("%s", _e)
    try:
        await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
    except Exception as e:
        log.warning("Diligence finish message failed: %s", e)


async def _timeout_watcher(bot, chat_id: int):
    """Ждёт таймаут ивента и заканчивает его если не финишировал досрочно."""
    await asyncio.sleep(_DILIGENCE_TIMEOUT)
    if _DILIGENCE_ACTIVE.get(chat_id):
        await _finish_event(bot, chat_id, f"таймаут {_DILIGENCE_TIMEOUT // 60} мин.")


async def _launch_diligence(bot, chat_id: int) -> bool:
    """Запускает ивент в чате. Возвращает False если уже активен."""
    if _DILIGENCE_ACTIVE.get(chat_id):
        return False
    _DILIGENCE_ACTIVE[chat_id] = True
    _DILIGENCE_CLICKS[chat_id].clear()
    _DILIGENCE_START[chat_id] = time.time()

    kb = _event_keyboard(chat_id)
    try:
        msg = await bot.send_message(
            chat_id,
            "🚚 <b>ДИЛИЖАНС ИЗ ЛИ ЮЭ!</b>\n\n"
            f"Нужно <b>{_DILIGENCE_GOAL} атак</b> чтобы его остановить!\n"
            f"⏰ Ивент закончится через <b>10 минут</b>.\n"
            f"👤 Лимит: {_CLICK_LIMIT} ударов на участника.\n\n"
            f"🏆 Награда: <b>{_DILIGENCE_REWARD} 🪙</b> делятся пропорционально!\n\n"
            f"[{'░' * 16}] 0/{_DILIGENCE_GOAL}",
            parse_mode="HTML",
            reply_markup=kb,
        )
        _DILIGENCE_MSG_ID[chat_id] = msg.message_id
    except Exception as e:
        log.warning("Launch diligence failed: %s", e)
        _DILIGENCE_ACTIVE[chat_id] = False
        return False

    asyncio.create_task(_timeout_watcher(bot, chat_id))
    return True


# ─── CMD: бот дилижанс ───────────────────────────────────────────────────────

@router.message(BotCommand("дилижанс", "diligence"), RankFilter("admin_senior"))
async def cmd_diligence(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Только в группах.")
        return
    chat_id = message.chat.id
    launched = await _launch_diligence(message.bot, chat_id)
    if not launched:
        await message.answer("⚠️ Дилижанс уже активен в этом чате!")


# ─── Фоновое обновление сообщения ────────────────────────────────────────────

async def _update_diligence_msg(message, chat_id: int):
    """Обновить текст сообщения дилижанса. Запускается фоновой задачей."""
    total = _total_clicks(chat_id)
    bar = _progress_bar(total)
    try:
        await message.edit_text(
            "🚚 <b>ДИЛИЖАНС ИЗ ЛИ ЮЭ!</b>\n\n"
            f"[{bar}] <b>{total}/{_DILIGENCE_GOAL}</b>\n"
            f"👥 Участников: {len(_DILIGENCE_CLICKS[chat_id])}\n"
            f"🏆 Котёл: <b>{_DILIGENCE_REWARD} 🪙</b>",
            parse_mode="HTML",
            reply_markup=_event_keyboard(chat_id),
        )
    except Exception as _e:
        _log.debug("%s", _e)


# ─── Callback: клик по кнопке ─────────────────────────────────────────────────

@router.callback_query(lambda c: c.data and c.data.startswith("diligence:"))
async def cb_diligence_click(callback: CallbackQuery):
    chat_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id

    if not _DILIGENCE_ACTIVE.get(chat_id):
        await callback.answer("⏹ Ивент уже закончился!", show_alert=True)
        return

    current_clicks = _DILIGENCE_CLICKS[chat_id].get(uid, 0)
    if current_clicks >= _CLICK_LIMIT:
        await callback.answer(
            f"⚠️ Лимит {_CLICK_LIMIT} ударов исчерпан!", show_alert=True,
        )
        return

    _DILIGENCE_CLICKS[chat_id][uid] = current_clicks + 1
    total = _total_clicks(chat_id)

    await callback.answer(f"⚔️ Удар! ({current_clicks + 1}/{_CLICK_LIMIT})")

    # Block 4: Add season XP for diligence participation (first click only)
    if current_clicks == 0:  # First click
        try:
            from database.db import add_season_xp
            await add_season_xp(uid, 5)  # +5 season XP for participating
        except Exception as _e:
            _log.debug("%s", _e)

    # Обновляем сообщение каждые 5 кликов — фоновая задача, не блокирует ответ
    if total % 5 == 0 and total < _DILIGENCE_GOAL:
        asyncio.create_task(_update_diligence_msg(callback.message, chat_id))

    if total >= _DILIGENCE_GOAL:
        asyncio.create_task(_finish_event(callback.message.bot, chat_id, "цель достигнута!"))
