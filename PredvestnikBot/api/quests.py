"""
api/quests.py — daily quest operations.

All functions are async; the mini app wraps them with async_to_sync.
"""


async def get_quest(uid: int, chat_id: int) -> dict:
    """Return current daily quest and progress. No side effects.

    Returns {quest: {type, goal, desc, xp, mora}, progress, completed, rewarded, today}.
    """
    from database.db import get_user_quest, get_quest_progress
    from utils.helpers import bot_today

    today = bot_today()
    quest = await get_user_quest(uid, chat_id, today)
    row = await get_quest_progress(uid, chat_id, today)

    return {
        "quest": {
            "type": quest["type"],
            "goal": quest["goal"],
            "desc": quest["desc"],
            "xp": quest["xp"],
            "mora": quest.get("mora", 5),
        },
        "progress": row["progress"] if row else 0,
        "completed": bool(row["completed"]) if row else False,
        "rewarded": bool(row["rewarded"]) if row else False,
        "today": today,
    }


async def reroll_quest(uid: int, chat_id: int) -> dict:
    """Spend QUEST_REROLL_PRICE mora to swap to a new random quest.

    Raises ValueError with Russian message on business errors.
    Returns {quest: {type, goal, desc, xp, mora}, cost, new_balance}.
    """
    from config import QUEST_REROLL_PRICE
    from database.db import deduct_mora, get_mora, get_quest_progress, reroll_user_quest
    from utils.helpers import bot_today

    today = bot_today()

    row = await get_quest_progress(uid, chat_id, today)
    if row and row["completed"]:
        raise ValueError("Задание уже выполнено — переброс не нужен")

    mora = await get_mora(uid, chat_id)
    balance = mora["balance"] if mora else 0
    if balance < QUEST_REROLL_PRICE:
        raise ValueError(f"Недостаточно Моры. Нужно {QUEST_REROLL_PRICE} 🪙")

    ok, new_bal = await deduct_mora(uid, chat_id, QUEST_REROLL_PRICE)
    if not ok:
        raise ValueError("Не удалось списать Мору")

    quest = await reroll_user_quest(uid, chat_id, today)
    return {
        "quest": {
            "type": quest["type"],
            "goal": quest["goal"],
            "desc": quest["desc"],
            "xp": quest["xp"],
            "mora": quest.get("mora", 5),
        },
        "cost": QUEST_REROLL_PRICE,
        "new_balance": new_bal,
    }
