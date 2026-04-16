"""api/roulette.py — simplified roulette with capped payouts.

Only simple bets are allowed: red/black/even/odd/low/high.
The system uses a fixed win rate with a small capped payout to avoid
economy-breaking spikes from direct-number bets.

Called by both Telegram bot handlers and the mini app views.
All public functions are async; the mini app wraps them with async_to_sync.
"""
import random
import logging
_log = logging.getLogger(__name__)


# European roulette number sets
_RED   = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
_BLACK = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}


def color_of(n: int) -> str:
    if n == 0:
        return "green"
    return "red" if n in _RED else "black"


def _pick_winning_number(bet_type: str) -> int:
    """Return a random number on the wheel that wins for the given bet_type."""
    if bet_type == "red":
        return random.choice(sorted(_RED))
    if bet_type == "black":
        return random.choice(sorted(_BLACK))
    if bet_type == "even":
        return random.choice(list(range(2, 37, 2)))
    if bet_type == "odd":
        return random.choice(list(range(1, 37, 2)))
    if bet_type == "low":
        return random.randint(1, 18)
    if bet_type == "high":
        return random.randint(19, 36)
    return random.randint(0, 36)


def _pick_losing_number(bet_type: str) -> int:
    """Return a random number on the wheel that loses for the given simple bet."""
    losers = [n for n in range(37) if _bet_gross(bet_type, n, 10) == 0]
    return random.choice(losers)


def _bet_gross(bet_type: str, number: int, bet_amount: int) -> int:
    """Return profit on a win (excluding original bet). 0 = loss."""
    col = color_of(number)
    capped_profit = max(1, int(round(bet_amount * 0.9)))

    if bet_type == "red":
        return capped_profit if col == "red" else 0
    if bet_type == "black":
        return capped_profit if col == "black" else 0
    if bet_type == "even":
        return capped_profit if (number > 0 and number % 2 == 0) else 0
    if bet_type == "odd":
        return capped_profit if (number > 0 and number % 2 == 1) else 0
    if bet_type == "low":
        return capped_profit if (1 <= number <= 18) else 0
    if bet_type == "high":
        return capped_profit if (19 <= number <= 36) else 0
    raise ValueError(f"Неизвестный тип ставки: {bet_type!r}")


async def _deliver_item_prize(
    uid: int, chat_id: int,
    item_key: str, item_name: str, item_type: str,
) -> dict:
    """Deliver a roulette item prize. All items go to gacha_inventory.

    Buffs apply immediately when activated from inventory.
    Food/consume items can be activated from inventory.
    """
    from database.db import add_gacha_item
    from shared_prices import ITEM_METADATA

    # ── Determine slot and rarity by item_type ────────────────────────────────
    if item_type == "food":
        slot   = "food"
        rarity = "common"
    elif item_type == "consume":
        slot   = "consume"
        rarity = "common"
    elif item_type == "coupon":
        meta   = ITEM_METADATA.get(item_key, {})
        slot   = meta.get("slot", "coupon")
        rarity = "rare"
    else:
        # buff and anything else
        meta   = ITEM_METADATA.get(item_key, {})
        slot   = meta.get("slot")
        rarity = "common"

    await add_gacha_item(
        uid, chat_id,
        item_key=item_key,
        item_name=item_name,
        rarity=rarity,
        atk=0, def_val=0, hp=0, crit_rate=0.0,
        slot=slot,
    )
    return {
        "item_key":  item_key,
        "item_name": item_name,
        "item_type": item_type,
        "effect":    "добавлен в инвентарь",
    }


async def roulette_spin(
    uid: int, chat_id: int,
    bet_type: str, bet_amount: int,
) -> dict:
    """
    Full roulette cycle: validate → deduct bet → spin → pay → optional item prize.

    bet_type:   "red" | "black" | "even" | "odd" | "low" | "high"
    bet_amount: ROULETTE_MIN_BET .. ROULETTE_MAX_BET

    Returns {ok, number, color, win, gross_profit, win_tax, net_prize, new_balance, item_prize}
    """
    from database.db import add_mora, add_to_treasury, get_mora
    from database.postgres import connect as postgres_connect
    from shared_prices import (
        ROULETTE_MIN_BET, ROULETTE_MAX_BET,
        ROULETTE_TAX, ROULETTE_ITEM_CHANCE, ROULETTE_WIN_RATE,
        ROULETTE_PRIZE_POOL, ROULETTE_PITY_BET_CAP,
    )

    if bet_amount < ROULETTE_MIN_BET:
        raise ValueError(f"Минимальная ставка: {ROULETTE_MIN_BET} 🪙")
    if bet_amount > ROULETTE_MAX_BET:
        raise ValueError(f"Максимальная ставка: {ROULETTE_MAX_BET} 🪙")

    _valid_simple = {"red", "black", "even", "odd", "low", "high"}
    if bet_type not in _valid_simple:
        raise ValueError("Доступны только простые ставки: красное, чёрное, чётное, нечётное, 1–18, 19–36")

    # ── Atomically read pity counter + deduct bet in ONE transaction ──────────
    async with postgres_connect() as db:
        row = await db.fetchone(
            "SELECT COALESCE(u.balance,0) AS balance, COALESCE(um.roulette_losses, 0) AS roulette_losses "
            "FROM users u LEFT JOIN user_mora um ON um.user_id=u.user_id AND um.chat_id=? "
            "WHERE u.user_id=?",
            (chat_id, uid),
        )
        if not row or row["balance"] < bet_amount:
            bal = row["balance"] if row else 0
            raise ValueError(f"Недостаточно Моры. У тебя: {bal} 🪙")
        losses = row["roulette_losses"]

        # ── Enforce pity bet cap to prevent "build pity with small bets" exploit ──
        if losses >= 3 and bet_amount > ROULETTE_PITY_BET_CAP:
            raise ValueError(
                f"⚠️ Активна полоса неудач ({losses} в ряд) — "
                f"максимальная ставка сейчас {ROULETTE_PITY_BET_CAP} 🪙"
            )

        cursor = await db.execute(
            "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
            (bet_amount, uid, bet_amount),
        )
        if cursor.rowcount == 0:
            raise ValueError("Недостаточно Моры")

    # ── Spin (with pity boost after losing streak) ────────────────────────────
    if losses >= 3:
        pity_boost = min(0.90, 0.40 + (losses - 2) * 0.15)
        win = random.random() < max(ROULETTE_WIN_RATE, pity_boost)
    else:
        win = random.random() < ROULETTE_WIN_RATE

    number = _pick_winning_number(bet_type) if win else _pick_losing_number(bet_type)

    color      = color_of(number)
    gross      = _bet_gross(bet_type, number, bet_amount)
    win        = gross > 0
    win_tax    = 0
    net_prize  = 0

    if win:
        win_tax      = max(1, int(gross * ROULETTE_TAX))
        net_prize    = gross - win_tax
        total_return = bet_amount + net_prize   # original stake + profit
        await add_to_treasury(chat_id, win_tax, "roulette", uid)
        new_bal = await add_mora(uid, chat_id, total_return)
    else:
        mora_row = await get_mora(uid, chat_id)
        new_bal  = mora_row["balance"] if mora_row else 0

    # ── Update pity (loss streak) counter ────────────────────────────────────
    async with postgres_connect() as db:
        if win:
            await db.execute(
                "UPDATE user_mora SET roulette_losses=0 WHERE user_id=? AND chat_id=?",
                (uid, chat_id),
            )
        else:
            await db.execute(
                "UPDATE user_mora SET roulette_losses=COALESCE(roulette_losses,0)+1 "
                "WHERE user_id=? AND chat_id=?",
                (uid, chat_id),
            )
        await db.commit()

    # ── Item prize (18% chance on any win) ────────────────────────────────────
    item_prize = None
    if win and ROULETTE_PRIZE_POOL and random.random() < ROULETTE_ITEM_CHANCE:
        try:
            weights = [w for (_, _, _, w) in ROULETTE_PRIZE_POOL]
            choice  = random.choices(ROULETTE_PRIZE_POOL, weights=weights, k=1)[0]
            i_key, i_name, i_type, _ = choice
            item_prize = await _deliver_item_prize(uid, chat_id, i_key, i_name, i_type)
        except Exception:
            _log.warning("item prize failed uid=%s pool_len=%d", uid, len(ROULETTE_PRIZE_POOL), exc_info=True)

    # Log to wallet ledger
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(uid, chat_id, "expense", bet_amount, "roulette", f"Ставка рулетки {bet_amount}🪙")
        if win and net_prize > 0:
            await log_wallet_tx(uid, chat_id, "income", net_prize, "roulette", f"Выигрыш рулетки {net_prize}🪙")
    except Exception as _e:
        _log.debug("%s", _e)

    # Achievement tracking for roulette spins (count only expense entries = one per spin)
    try:
        from database.postgres import connect as _pg_conn
        async with _pg_conn() as _db:
            _row = await _db.fetchone(
                "SELECT COUNT(*) AS c FROM wallet_ledger "
                "WHERE user_id=? AND chat_id=? AND source='roulette' AND type='expense'",
                (uid, chat_id),
            )
        _spin_count = int(_row["c"]) if _row else 1
        from api.achievements import check_and_award as _ach
        import asyncio
        asyncio.create_task(_ach(uid, chat_id, "roulette", _spin_count))
    except Exception as _e:
        _log.debug("%s", _e)

    return {
        "ok":          True,
        "number":      number,
        "color":       color,
        "win":         win,
        "gross_profit": gross,
        "win_tax":     win_tax,
        "net_prize":   net_prize,
        "new_balance": new_bal,
        "item_prize":  item_prize,
    }
