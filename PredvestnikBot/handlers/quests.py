"""
Ежедневные задания: бот задание
"""
from datetime import date

from aiogram import Router
from aiogram.types import Message

from database.db import get_quest_progress, get_todays_quest
from filters.bot_command import BotCommand

router = Router()


@router.message(BotCommand("задание", "quest", "квест", "задания"))
async def cmd_quest(message: Message, cmd_args: str):
    quest = get_todays_quest()
    today = date.today().isoformat()
    row = await get_quest_progress(message.from_user.id, message.chat.id, today)

    progress  = row["progress"]  if row else 0
    completed = bool(row["completed"]) if row else False
    rewarded  = bool(row["rewarded"])  if row else False
    goal      = quest["goal"]
    xp_reward = quest["xp"]

    bar_filled = min(10, int(progress / goal * 10)) if goal else 0
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    if completed and rewarded:
        status = "✅ Выполнено! Бонус получен."
    elif completed:
        status = "✅ Выполнено!"
    else:
        status = f"⏳ Прогресс: {progress}/{goal}"

    await message.answer(
        f"📋 <b>Ежедневное задание</b>\n\n"
        f"🎯 {quest['desc']}\n"
        f"🏆 Награда: <b>+{xp_reward} XP</b>\n\n"
        f"[{bar}]  {progress}/{goal}\n"
        f"{status}\n\n"
        f"<i>Задание обновляется каждый день автоматически.</i>",
        parse_mode="HTML",
    )
