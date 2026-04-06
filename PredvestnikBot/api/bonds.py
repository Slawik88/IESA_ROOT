"""
api/bonds.py — unified bond trading operations.

All functions are async; the mini app wraps them with async_to_sync.
"""


async def buy_bond(uid: int, chat_id: int, bond_key: str,
                   amount: int, wallet: str = "personal") -> dict:
    """
    Buy `amount` units of `bond_key`.

    wallet: "personal" | "family"
    Raises ValueError on error.
    Returns {ok, bond_key, price_per, total_cost, holdings, invested, personal, family}
    """
    from database.db import (
        add_mora, buy_bonds, get_bond_prices, get_mora,
        get_user_bonds, is_user_single,
    )

    try:
        from config import BOND_DEFAULTS
    except Exception:
        from shared_prices import BOND_DEFAULTS

    if bond_key not in BOND_DEFAULTS:
        raise ValueError(f"Неизвестная облигация: {bond_key}")
    if amount <= 0:
        raise ValueError("Количество должно быть > 0")
    if wallet not in ("personal", "family"):
        wallet = "personal"

    prices    = await get_bond_prices(chat_id)
    price_per = prices.get(bond_key, BOND_DEFAULTS[bond_key]["base_price"])
    total_cost = price_per * amount

    # ── Exchange limit: a single user cannot invest more than 10 000 Mora total ──
    EXCHANGE_LIMIT = 10_000
    user_bonds_now = await get_user_bonds(uid, chat_id)
    total_already_invested = sum(b["invested"] for b in user_bonds_now)
    if total_already_invested + total_cost > EXCHANGE_LIMIT:
        remaining = max(0, EXCHANGE_LIMIT - total_already_invested)
        raise ValueError(
            f"Лимит Биржи: нельзя вложить суммарно более {EXCHANGE_LIMIT} 🪙. "
            f"Уже вложено: {total_already_invested} 🪙. "
            f"Доступно ещё: {remaining} 🪙."
        )

    if wallet == "family":
        single = await is_user_single(uid, chat_id)
        if single:
            raise ValueError("Нет семейного кошелька")
        # Use pair-aware atomic deduction (FOR UPDATE, combined pool of both partners)
        from database.db import deduct_family_pool, get_total_family_balance
        total_fbal, _my, partner_id = await get_total_family_balance(chat_id, uid)
        if total_fbal < total_cost:
            raise ValueError(f"Недостаточно в семейном ({total_fbal}/{total_cost} 🪙)")
        await deduct_family_pool(chat_id, uid, partner_id, total_cost)
    else:
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            cursor = await db.execute(
                "UPDATE users SET balance=balance-? WHERE user_id=? AND COALESCE(balance,0)>=?",
                (total_cost, uid, total_cost),
            )
            if cursor.rowcount == 0:
                mora_row = await get_mora(uid, chat_id)
                bal = mora_row["balance"] if mora_row else 0
                raise ValueError(f"Недостаточно Моры ({bal}/{total_cost} 🪙)")
            await db.commit()

    await buy_bonds(uid, chat_id, bond_key, amount, price_per)

    # Log to wallet ledger
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(uid, chat_id, "expense", total_cost, "bonds_buy",
                            f"{bond_key} ×{amount} по {price_per}🪙")
    except Exception:
        pass

    # Return updated balances
    mora_row    = await get_mora(uid, chat_id)
    personal    = mora_row["balance"] if mora_row else 0
    family      = 0
    try:
        from database.db import get_total_family_balance
        total_fbal, _my, _pid = await get_total_family_balance(chat_id, uid)
        family = total_fbal
    except Exception:
        pass

    # Holdings after purchase
    user_bonds  = await get_user_bonds(uid, chat_id)
    bond_record = next((b for b in user_bonds if b["bond_key"] == bond_key), None)
    holdings    = bond_record["amount"]   if bond_record else amount
    invested    = bond_record["invested"] if bond_record else total_cost

    return {
        "ok":         True,
        "bond_key":   bond_key,
        "price_per":  price_per,
        "total_cost": total_cost,
        "holdings":   holdings,
        "invested":   invested,
        "personal":   personal,
        "family":     family,
    }


async def sell_bond(uid: int, chat_id: int, bond_key: str, amount: int) -> dict:
    """
    Sell `amount` units of `bond_key` (FIFO).

    Progressive profit tax → treasury.
    Raises ValueError on error.
    Returns {ok, bond_key, sold, price_per, revenue, profit, tax, remaining, balance}
    """
    from database.db import (
        add_to_treasury, get_bond_prices, get_mora, get_user_bonds, sell_bonds,
    )

    try:
        from config import BOND_DEFAULTS
    except Exception:
        from shared_prices import BOND_DEFAULTS

    if bond_key not in BOND_DEFAULTS:
        raise ValueError("Неизвестная облигация")
    if amount <= 0:
        raise ValueError("Количество должно быть > 0")

    user_bonds  = await get_user_bonds(uid, chat_id)
    bond_record = next((b for b in user_bonds if b["bond_key"] == bond_key), None)
    have        = bond_record["amount"] if bond_record else 0
    if have < amount:
        raise ValueError(f"У тебя только {have} облигаций {bond_key}")

    prices    = await get_bond_prices(chat_id)
    price_per = prices.get(bond_key, BOND_DEFAULTS[bond_key]["base_price"])
    revenue   = price_per * amount

    # Progressive profit tax on net gain (FIFO average)
    avg_buy  = (bond_record["invested"] / bond_record["amount"]) if bond_record and bond_record["amount"] > 0 else price_per
    profit   = max(0, int((price_per - avg_buy) * amount))
    if profit <= 50:
        bond_tax = max(0, int(profit * 0.10))
    elif profit <= 100:
        bond_tax = int(profit * 0.20)
    elif profit <= 1_800:
        bond_tax = int(profit * 0.30)
    else:
        bond_tax = int(profit * 0.40)
    net_revenue = revenue - bond_tax

    ok, _ = await sell_bonds(uid, chat_id, bond_key, amount, credit_mora=net_revenue)
    if not ok:
        raise ValueError("Не удалось оформить продажу")

    # mora already credited atomically inside sell_bonds; fetch current balance
    _m = await get_mora(uid, chat_id)
    new_balance = _m["balance"] if _m else 0
    if bond_tax > 0:
        await add_to_treasury(chat_id, bond_tax, "bonds", uid)

    # Log to wallet ledger
    try:
        from api.economy import log_wallet_tx
        await log_wallet_tx(uid, chat_id, "income", net_revenue, "bonds_sell",
                            f"{bond_key} ×{amount} по {price_per}🪙")
    except Exception:
        pass

    remaining = have - amount

    return {
        "ok":         True,
        "bond_key":   bond_key,
        "sold":       amount,
        "price_per":  price_per,
        "revenue":    net_revenue,
        "profit":     profit,
        "tax":        bond_tax,
        "remaining":  remaining,
        "balance":    new_balance,
    }


async def get_portfolio(uid: int, chat_id: int) -> dict:
    """
    Returns the user's bond portfolio with current prices and unrealised P&L.
    """
    from database.db import get_bond_prices, get_user_bonds

    try:
        from config import BOND_DEFAULTS
    except Exception:
        from shared_prices import BOND_DEFAULTS

    user_bonds = await get_user_bonds(uid, chat_id)
    prices     = await get_bond_prices(chat_id)

    holdings = []
    for b in user_bonds:
        if b["amount"] <= 0:
            continue
        key       = b["bond_key"]
        cur_price = prices.get(key, BOND_DEFAULTS.get(key, {}).get("base_price", 0))
        cur_val   = cur_price * b["amount"]
        pnl       = cur_val - b["invested"]
        holdings.append({
            "bond_key":       key,
            "amount":         b["amount"],
            "invested":       b["invested"],
            "current_value":  cur_val,
            "current_price":  cur_price,
            "pnl":            pnl,
        })

    all_prices = {
        k: {"price": prices.get(k, v["base_price"]),
            "label": v.get("label", k),
            "base_price": v["base_price"]}
        for k, v in BOND_DEFAULTS.items()
    }

    return {
        "holdings":   holdings,
        "prices":     all_prices,
    }


async def get_bonds_status(uid: int, chat_id: int) -> dict:
    """Full bonds page payload: prices, user holdings, history, market trend.

    Returns the same shape the miniapp_bonds GET view expects.
    """
    from database.db import get_bond_price_history, get_bond_prices, get_user_bonds

    try:
        from config import BOND_DEFAULTS
    except Exception:
        from shared_prices import BOND_DEFAULTS

    bond_keys = list(BOND_DEFAULTS.keys())

    # Current prices
    prices = await get_bond_prices(chat_id)

    # User holdings
    user_bonds = await get_user_bonds(uid, chat_id)
    holdings = {b["bond_key"]: {"amount": b["amount"], "invested": b["invested"]} for b in user_bonds}

    # Price history (last 120 ticks per bond, oldest first)
    history = {}
    for bk in bond_keys:
        rows = await get_bond_price_history(chat_id, bk, limit=120)
        history[bk] = [{"price": r["price"], "ts": str(r["recorded_at"])} for r in rows]

    # Market trend
    from database.postgres import connect as postgres_connect
    market_trend = "neutral"
    market_ticks = 0
    try:
        async with postgres_connect() as db:
            async with db.execute(
                "SELECT trend, ticks_left FROM market_state WHERE chat_id=?",
                (chat_id,),
            ) as c:
                state_row = await c.fetchone()
        if state_row:
            market_trend = state_row["trend"]
            market_ticks = state_row["ticks_left"]
    except Exception:
        pass

    bonds_out = []
    for bk in bond_keys:
        current_price = prices.get(bk, BOND_DEFAULTS[bk]["base_price"])
        holding = holdings.get(bk, {"amount": 0, "invested": 0})
        amount = holding["amount"]
        invested = holding["invested"]
        bname = BOND_DEFAULTS.get(bk, {}).get("name", bk)
        avg_price = round(invested / amount, 1) if amount > 0 else 0
        pnl_mora = amount * current_price - invested if amount > 0 else 0
        pnl_pct = round(pnl_mora / invested * 100, 1) if invested > 0 else 0
        bonds_out.append({
            "key":       bk,
            "name":      bname,
            "price":     current_price,
            "amount":    amount,
            "invested":  invested,
            "avg_price": avg_price,
            "pnl_mora":  pnl_mora,
            "pnl_pct":   pnl_pct,
            "value":     amount * current_price,
            "history":   history.get(bk, []),
        })

    # Timestamp of last price update — used by the mini app to detect price changes
    prices_updated_at = ""
    try:
        from database.db import get_scheduler_state
        prices_updated_at = await get_scheduler_state("bond_price_last_updated_at") or ""
    except Exception:
        pass

    return {
        "bonds":              bonds_out,
        "market_trend":       market_trend,
        "market_ticks":       market_ticks,
        "prices_updated_at":  prices_updated_at,
    }
