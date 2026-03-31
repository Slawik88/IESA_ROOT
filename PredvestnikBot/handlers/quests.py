"""
Ежедневные задания: бот задание / бот перебросить задание
"""
from aiogram import Router
from aiogram.types import Message

from config import QUEST_REROLL_PRICE
from database.db import get_mora, get_quest_progress, get_user_quest, reroll_user_quest
from filters.bot_command import BotCommand
from utils.helpers import bot_today

router = Router()


@router.message(BotCommand("задание", "quest", "квест", "задания"))
async def cmd_quest(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Задания доступны только в группах.")
        return
    today = bot_today()
    quest = await get_user_quest(message.from_user.id, message.chat.id, today)
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
        f"<i>Задание обновляется каждый день автоматически.</i>\n"
        f"<i>Сменить задание: <code>бот перебросить задание</code> ({QUEST_REROLL_PRICE} 🪙)</i>",
        parse_mode="HTML",
    )


@router.message(BotCommand("перебросить задание", "перебросить квест", "quest reroll", "сменить задание"))
async def cmd_reroll_quest(message: Message, cmd_args: str):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("❌ Команда доступна только в группах.")
        return

    uid = message.from_user.id
    chat_id = message.chat.id
    today = bot_today()

    # Проверяем, не выполнено ли уже сегодня
    row = await get_quest_progress(uid, chat_id, today)
    if row and row["completed"]:
        await message.answer(
            "✅ Ты уже выполнил сегодняшнее задание — переброс не нужен!",
        )
        return

    mora = await get_mora(uid, chat_id)
    bal = mora["balance"] if mora else 0
    if bal < QUEST_REROLL_PRICE:
        await message.answer(
            f"❌ Переброс задания стоит <b>{QUEST_REROLL_PRICE} 🪙</b>.\n"
            f"У тебя: <b>{bal} 🪙</b>.",
            parse_mode="HTML",
        )
        return

    from database.postgres import connect as postgres_connect
    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (QUEST_REROLL_PRICE, uid, QUEST_REROLL_PRICE),
        )
        if cursor.rowcount == 0:
            await message.answer("❌ Не удалось списать Мору.")
            return
        await db.commit()
        async with db.execute(
            "SELECT COALESCE(balance, 0) AS balance FROM users WHERE user_id=?",
            (uid,),
        ) as c:
            row = await c.fetchone()
        new_bal = row[0] if row else 0

    quest = await reroll_user_quest(uid, chat_id, today)

    await message.answer(
        f"🔄 <b>Задание сброшено!</b>  (<b>-{QUEST_REROLL_PRICE} 🪙</b>)\n"
        f"Твой баланс: <b>{new_bal} 🪙</b>\n\n"
        f"📋 <b>Новое задание:</b>\n"
        f"🎯 {quest['desc']}\n"
        f"🏆 Награда: <b>+{quest['xp']} XP</b>",
        parse_mode="HTML",
    )
