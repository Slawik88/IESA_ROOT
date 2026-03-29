"""
api/casino.py — unified coin flip logic.

Called by both the Telegram bot handlers and the mini app views.
All public functions are async; the mini app wraps them with async_to_sync.
"""
import logging
import random

# House win rate — single source of truth
COIN_WIN_RATE = 0.50  # 50% chance of winning


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
        try:
            from api.economy import log_wallet_tx
            await log_wallet_tx(uid, chat_id, "income", prize, "casino", f"Выигрыш {prize}🪙")
        except Exception:
            pass
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
        logging.getLogger(__name__).warning("quest_tick failed uid=%s chat=%s", uid, chat_id, exc_info=True)

    # Increment coinflip counter & check achievements (fire-and-forget)
    try:
        from database.db import postgres_connect as _pg
        async with _pg() as _db:
            await _db.execute(
                "UPDATE user_mora SET total_coinflip = COALESCE(total_coinflip,0) + 1 WHERE user_id=? AND chat_id=?",
                (uid, chat_id)
            )
            row = await _db.fetchone("SELECT total_coinflip FROM user_mora WHERE user_id=? AND chat_id=?", (uid, chat_id))
            total_cf = int(row["total_coinflip"] or 0) if row else 1
        from api.achievements import check_and_award as _ach
        await _ach(uid, chat_id, "coinflip", total_cf)
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
    from database.db import get_mora
    from database.postgres import connect as postgres_connect

    try:
        from config import COIN_MAX_BET
    except Exception:
        COIN_MAX_BET = 5000

    if bet <= 0:
        raise ValueError("Ставка должна быть > 0")
    if bet > COIN_MAX_BET:
        raise ValueError(f"Максимальная ставка: {COIN_MAX_BET} 🪙")

    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE user_mora SET balance=balance-? WHERE user_id=? AND chat_id=? AND balance>=?",
            (bet, uid, chat_id, bet),
        )
        if cursor.rowcount == 0:
            mora_row = await get_mora(uid, chat_id)
            bal = mora_row["balance"] if mora_row else 0
            raise ValueError(f"Недостаточно Моры. У тебя: {bal} 🪙")
        await db.commit()

    # Log bet as expense
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(uid, chat_id, "expense", bet, "casino", f"Ставка {bet}🪙")
    except Exception:
        pass

    return await coin_flip_resolve(uid, chat_id, bet)


# ─── Lottery ──────────────────────────────────────────────────────────────────

def _week_key() -> str:
    """ISO week key like '2026-W13'."""
    from datetime import date
    iso = date.today().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


async def get_lottery_status(uid: int, chat_id: int) -> dict:
    """Return current lottery ticket count for this week.

    Returns {ok, tickets, week, ticket_price}.
    """
    from database.db import get_lottery_tickets

    try:
        from config import LOTTERY_TICKET_PRICE
    except Exception:
        LOTTERY_TICKET_PRICE = 10

    week = _week_key()
    tickets = await get_lottery_tickets(chat_id, uid, week)

    return {
        "ok": True,
        "tickets": tickets,
        "week": week,
        "ticket_price": LOTTERY_TICKET_PRICE,
    }


async def buy_lottery_ticket(uid: int, chat_id: int) -> dict:
    """Buy one lottery ticket for the current week.

    Raises ValueError on insufficient balance.
    Returns {ok, tickets, ticket_price, new_balance}.
    """
    from database.db import get_mora
    from database.db import buy_lottery_ticket as _db_buy_ticket
    from database.postgres import connect as postgres_connect

    try:
        from config import LOTTERY_TICKET_PRICE
    except Exception:
        LOTTERY_TICKET_PRICE = 10

    async with postgres_connect() as db:
        cursor = await db.execute(
            "UPDATE user_mora SET balance=balance-? WHERE user_id=? AND chat_id=? AND balance>=?",
            (LOTTERY_TICKET_PRICE, uid, chat_id, LOTTERY_TICKET_PRICE),
        )
        if cursor.rowcount == 0:
            mora_row = await get_mora(uid, chat_id)
            bal = mora_row["balance"] if mora_row else 0
            raise ValueError(f"Нужно {LOTTERY_TICKET_PRICE} 🪙")
        await db.commit()

    week = _week_key()
    tickets = await _db_buy_ticket(chat_id, uid, week)

    # 10% НДС from lottery tickets → treasury
    from database.db import add_to_treasury
    lottery_tax = max(1, int(LOTTERY_TICKET_PRICE * 0.10))
    await add_to_treasury(chat_id, lottery_tax, "lottery_ticket", uid)

    async with postgres_connect() as db:
        async with db.execute(
            "SELECT balance FROM user_mora WHERE user_id=? AND chat_id=?",
            (uid, chat_id),
        ) as c:
            row = await c.fetchone()
    new_balance = row[0] if row else 0

    return {
        "ok": True,
        "tickets": tickets,
        "ticket_price": LOTTERY_TICKET_PRICE,
        "new_balance": new_balance,
    }
