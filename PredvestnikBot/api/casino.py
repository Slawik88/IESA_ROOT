"""
api/casino.py — unified coin flip logic.

Called by both the Telegram bot handlers and the mini app views.
All public functions are async; the mini app wraps them with async_to_sync.
"""
import random

# House win rate — single source of truth
COIN_WIN_RATE = 0.40  # 40 % chance of winning


async def coin_flip_resolve(uid: int, chat_id: int, bet: int) -> dict:
    """
    Resolve a coin flip where the bet has ALREADY been deducted from the user's balance.

    Returns:
        {ok, win, bet, prize, win_tax, new_balance, quest_done, quest_xp, quest_mora}
    """
    from database.db import (
        add_mora, add_to_treasury, get_mora,
        get_user_quest, quest_tick, mark_quest_rewarded, add_xp_in_chat,
    )
    from utils.helpers import bot_today

    win     = random.random() < COIN_WIN_RATE
    win_tax = 0
    prize   = 0

    if win:
        win_tax = max(1, int(bet * 0.05))
        prize   = bet * 2 - win_tax
        await add_to_treasury(chat_id, win_tax, "coinflip", uid)
        new_bal = await add_mora(uid, chat_id, prize)
    else:
        mora_row = await get_mora(uid, chat_id)
        new_bal  = mora_row["balance"] if mora_row else 0

    # Quest tick
    quest_done = quest_xp = quest_mora = 0
    try:
        today = bot_today()
        quest = await get_user_quest(uid, chat_id, today)
        if quest.get("type") == "coinflip":
            _new_p, _goal, just_done = await quest_tick(uid, chat_id, today, quest["type"], quest["goal"])
            if just_done:
                quest_mora = quest.get("mora", 5)
                quest_xp   = quest.get("xp", 10)
                await add_xp_in_chat(uid, chat_id, quest_xp)
                await add_mora(uid, chat_id, quest_mora)
                await mark_quest_rewarded(uid, chat_id, today)
                quest_done = 1
    except Exception:
        pass

    return {
        "ok":          True,
        "win":         win,
        "bet":         bet,
        "prize":       prize,
        "win_tax":     win_tax,
        "new_balance": new_bal,
        "quest_done":  bool(quest_done),
        "quest_xp":    int(quest_xp),
        "quest_mora":  int(quest_mora),
    }


async def coin_flip(uid: int, chat_id: int, bet: int) -> dict:
    """
    Full coin flip: validate + deduct bet + resolve + quest tick.

    Use from the mini app (single atomic call).
    Bot handlers should use coin_flip_resolve() after deducting separately.

    Raises ValueError with a user-friendly Russian message on any error.
    """
    from database.db import deduct_mora, get_mora

    try:
        from config import COIN_MAX_BET
    except Exception:
        COIN_MAX_BET = 5000

    if bet <= 0:
        raise ValueError("Ставка должна быть > 0")
    if bet > COIN_MAX_BET:
        raise ValueError(f"Максимальная ставка: {COIN_MAX_BET} 🪙")

    mora_row = await get_mora(uid, chat_id)
    bal = mora_row["balance"] if mora_row else 0
    if bal < bet:
        raise ValueError(f"Недостаточно Моры. У тебя: {bal} 🪙")

    ok, _ = await deduct_mora(uid, chat_id, bet)
    if not ok:
        raise ValueError("Не удалось списать ставку")

    return await coin_flip_resolve(uid, chat_id, bet)
