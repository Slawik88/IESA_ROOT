"""
🗓 Ежедневный чекин — стрики, чекпоинты, награды.

Команды:
  бот чекин / бот daily  — ежедневная отметка (мора + стрик)
  бот стрик              — посмотреть текущий стрик без отметки
"""

import html
from aiogram import Router
from aiogram.types import Message

from database.db import add_mora, get_daily_checkin, perform_checkin
from filters.bot_command import BotCommand

router = Router()

# Таблица наград (день → мора)
_REWARDS = {
    1: 30, 2: 30, 3: 35, 4: 35, 5: 60,
    6: 40, 7: 40, 8: 45, 9: 45, 10: 80,
    11: 50, 12: 50, 13: 55, 14: 55, 15: 100,
    16: 60, 17: 60, 18: 70, 19: 70, 20: 150,
}
_CHECKPOINTS = {5, 10, 15, 20}


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
    cmd_text = (message.text or "").split()[1].lower() if len((message.text or "").split()) > 1 else ""
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

    result = await perform_checkin(uid, chat_id)

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

    # Начислить мору
    mora_reward = result["mora"]
    await add_mora(uid, chat_id, mora_reward)

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

    await message.answer("\n".join(lines), parse_mode="HTML")
