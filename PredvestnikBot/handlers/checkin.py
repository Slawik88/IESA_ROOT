"""
🗓 Ежедневный чекин — стрики, чекпоинты, награды.

Команды:
  бот чекин / бот daily  — ежедневная отметка (мора + стрик)
  бот стрик              — посмотреть текущий стрик без отметки
"""

import html
from aiogram import Router
from aiogram.types import Message

from database.db import get_daily_checkin
from api.checkin import do_checkin
from filters.bot_command import BotCommand
from shared_prices import CHECKIN_REWARDS as _REWARDS, CHECKIN_CHECKPOINTS as _CHECKPOINTS

from filters.chat_mode import MainChatOnly
import logging
_log = logging.getLogger(__name__)
router = Router()
router.message.filter(MainChatOnly())



def _render_calendar(streak: int) -> str:
    """Сформировать текстовый календарь 20 дней."""
    lines = []
    row = []
    for day in range(1, 21):
        mora = _REWARDS.get(day, 40)
        if day <= streak:
            cell = f"[✅{day}]"
        elif day == streak + 1:
            cell = f"[⭐{day}]"
        elif day in _CHECKPOINTS:
            cell = f"[🏆{day}]"
        else:
            cell = f"[{day}]"
        row.append(cell)
        if len(row) == 5:
            lines.append("  ".join(row))
            row = []
    if row:
        lines.append("  ".join(row))
    return "\n".join(lines)


@router.message(BotCommand("чекин", "daily", "check-in", "checkin", "отметка", "стрик"))
async def cmd_checkin(message: Message, cmd_args: str):
    uid = message.from_user.id
    chat_id = message.chat.id

    if message.chat.type == "private":
        await message.answer("❌ Чекин доступен только в групповых чатах.")
        return

    # Только просмотр стрика
    cmd_text = cmd_args.strip().lower()
    if cmd_text == "стрик":
        data = await get_daily_checkin(uid, chat_id)
        streak = data["streak"]
        total = data["total_days"]
        cal = _render_calendar(streak)
        await message.answer(
            f"📅 <b>Твой стрик</b>\n\n"
            f"🔥 Текущий: <b>{streak} дней</b>\n"
            f"📊 Всего отмечено: <b>{total} дней</b>\n\n"
            f"<pre>{cal}</pre>",
            parse_mode="HTML",
        )
        return

    result = await do_checkin(uid, chat_id)

    if result.get("already_done"):
        data = await get_daily_checkin(uid, chat_id)
        cal = _render_calendar(data["streak"])
        await message.answer(
            f"⏳ Ты уже отметился сегодня!\n\n"
            f"🔥 Стрик: <b>{data['streak']} дней</b>\n\n"
            f"<pre>{cal}</pre>",
            parse_mode="HTML",
        )
        return

    mora_reward = result["mora"]

    streak = result["streak"]
    total = result["total_days"]
    cal = _render_calendar(streak)

    lines = [
        f"✅ <b>Чекин засчитан!</b>",
        f"",
        f"💰 Награда: <b>+{mora_reward} 🪙</b>",
        f"🔥 Стрик: <b>{streak} дней</b>",
        f"📊 Всего отмечено: <b>{total} дней</b>",
    ]

    if result.get("is_checkpoint"):
        lines.append(f"")
        lines.append(f"🏆 <b>Чекпоинт {streak} дней!</b> Стрик сохранён.")

    if result.get("free_gacha"):
        lines.append(f"")
        lines.append(f"🌟 <b>День 20 — бесплатная молитва!</b>")
        lines.append(f"Используй: <code>бот молитва</code>")
        # Фактически выдаём бесплатный ролл через нулевую трату
        # (флаг free_gacha проверяется отдельно в обработчике гачи если нужно)

    lines += ["", f"<pre>{cal}</pre>"]

    # Block 4: Add season XP for checkin
    try:
        from database.db import add_season_xp
        season_result = await add_season_xp(uid, 10)  # +10 season XP
        if season_result and season_result.get("level_up"):
            lines.append(f"")
            lines.append(f"🌟 <b>Season Pass: Уровень {season_result['new_level']}!</b>")
    except Exception as _e:
        _log.debug("%s", _e)  # Безопасно игнорируем ошибки season XP

    await message.answer("\n".join(lines), parse_mode="HTML")
