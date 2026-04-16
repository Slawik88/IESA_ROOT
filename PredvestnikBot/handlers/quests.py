"""
Ежедневные задания: бот задание / бот перебросить задание
"""
from aiogram import Router
from aiogram.types import Message

from config import QUEST_REROLL_PRICE
from database.db import get_mora, get_quest_progress, get_user_quest, reroll_user_quest
from filters.bot_command import BotCommand
from utils.helpers import bot_today

from filters.chat_mode import MainChatOnly
router = Router()
router.message.filter(MainChatOnly())



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
        f"🏆 Награда: <b>+{xp_reward} XP  +{quest.get('mora', 0)} 🪙</b>\n\n"
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

    # Используем api.quests.reroll_quest, которая проверяет купоны
    from api.quests import reroll_quest
    from database.postgres import connect as postgres_connect

    # Проверяем наличие купона реролла
    has_coupon = False
    async with postgres_connect() as db:
        async with db.execute(
            "SELECT id FROM gacha_inventory WHERE user_id=? AND item_key='quest_reroll' AND COALESCE(stack_count,1)>0 LIMIT 1",
            (uid,),
        ) as c:
            coupon_row = await c.fetchone()
        has_coupon = bool(coupon_row)

    try:
        result = await reroll_quest(uid, chat_id, use_coupon=has_coupon)
    except ValueError as e:
        await message.answer(f"❌ {e}", parse_mode="HTML")
        return

    quest = result["quest"]
    if result.get("used_coupon"):
        cost_text = "🎫 Использован купон реролла (бесплатно)"
    else:
        cost_text = f"Списано: <b>-{result['cost']} 🪙</b>"

    await message.answer(
        f"🔄 <b>Задание сброшено!</b>  ({cost_text})\n"
        f"Твой баланс: <b>{result['new_balance']} 🪙</b>\n\n"
        f"📋 <b>Новое задание:</b>\n"
        f"🎯 {quest['desc']}\n"
        f"🏆 Награда: <b>+{quest['xp']} XP  +{quest.get('mora', 0)} 🪙</b>",
        parse_mode="HTML",
    )
