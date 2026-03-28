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


async def reroll_quest(uid: int, chat_id: int, use_coupon: bool = False) -> dict:
    """Spend QUEST_REROLL_PRICE mora to swap to a new random quest, or use a coupon for free.

    Raises ValueError with Russian message on business errors.
    Returns {quest: {type, goal, desc, xp, mora}, cost, new_balance, used_coupon}.
    """
    from config import QUEST_REROLL_PRICE
    from database.db import get_mora, get_quest_progress, reroll_user_quest
    from database.postgres import connect as postgres_connect
    from utils.helpers import bot_today

    today = bot_today()

    row = await get_quest_progress(uid, chat_id, today)
    if row and row["completed"]:
        raise ValueError("Задание уже выполнено — переброс не нужен")

    coupon_used = False
    if use_coupon:
        async with postgres_connect() as db:
            async with db.execute(
                "SELECT id, COALESCE(stack_count, 1) FROM gacha_inventory "
                "WHERE user_id=? AND chat_id=? AND item_key='quest_reroll' LIMIT 1",
                (uid, chat_id),
            ) as c:
                coupon_row = await c.fetchone()
            if not coupon_row:
                raise ValueError("Купон реролла не найден в инвентаре")
            cid, csc = coupon_row[0], coupon_row[1]
            if csc <= 1:
                await db.execute("DELETE FROM gacha_inventory WHERE id=?", (cid,))
            else:
                await db.execute(
                    "UPDATE gacha_inventory SET stack_count = stack_count - 1 WHERE id=?", (cid,)
                )
            await db.commit()
        coupon_used = True
        cost = 0
        mora = await get_mora(uid, chat_id)
        new_bal = mora["balance"] if mora else 0
    else:
        mora = await get_mora(uid, chat_id)
        balance = mora["balance"] if mora else 0
        if balance < QUEST_REROLL_PRICE:
            raise ValueError(f"Недостаточно Моры. Нужно {QUEST_REROLL_PRICE} 🪙")

        async with postgres_connect() as db:
            cursor = await db.execute(
                "UPDATE user_mora SET balance=balance-? WHERE user_id=? AND chat_id=? AND balance>=?",
                (QUEST_REROLL_PRICE, uid, chat_id, QUEST_REROLL_PRICE),
            )
            if cursor.rowcount == 0:
                raise ValueError("Не удалось списать Мору")
            await db.commit()
            async with db.execute(
                "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
                (uid, chat_id),
            ) as c:
                row = await c.fetchone()
            new_bal = row[0] if row else 0
        cost = QUEST_REROLL_PRICE

    quest = await reroll_user_quest(uid, chat_id, today)
    return {
        "quest": {
            "type": quest["type"],
            "goal": quest["goal"],
            "desc": quest["desc"],
            "xp": quest["xp"],
            "mora": quest.get("mora", 5),
        },
        "cost": cost,
        "new_balance": new_bal,
        "used_coupon": coupon_used,
    }
