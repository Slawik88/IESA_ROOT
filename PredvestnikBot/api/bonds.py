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
        add_mora, buy_bonds, deduct_mora, get_bond_prices, get_mora,
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

    if wallet == "family":
        single = await is_user_single(uid, chat_id)
        if single:
            raise ValueError("Нет семейного кошелька")
        from database.postgres import connect as postgres_connect
        async with postgres_connect() as db:
            async with db.execute(
                "SELECT COALESCE(balance,0) FROM family_wallet WHERE chat_id=? AND user_id=?",
                (chat_id, uid),
            ) as c:
                row = await c.fetchone()
            fam_bal = row[0] if row else 0
            if fam_bal < total_cost:
                raise ValueError(f"Недостаточно в семейном ({fam_bal}/{total_cost} 🪙)")
            await db.execute(
                "UPDATE family_wallet SET balance=balance-? WHERE chat_id=? AND user_id=? AND balance>=?",
                (total_cost, chat_id, uid, total_cost),
            )
            await db.commit()
    else:
        ok, _ = await deduct_mora(uid, chat_id, total_cost)
        if not ok:
            mora_row = await get_mora(uid, chat_id)
            bal = mora_row["balance"] if mora_row else 0
            raise ValueError(f"Недостаточно Моры ({bal}/{total_cost} 🪙)")

    await buy_bonds(uid, chat_id, bond_key, amount, price_per)

    # Return updated balances
    mora_row    = await get_mora(uid, chat_id)
    personal    = mora_row["balance"] if mora_row else 0
    family      = 0
    from database.postgres import connect as postgres_connect
    try:
        async with postgres_connect() as db:
            async with db.execute(
                "SELECT COALESCE(balance,0) FROM family_wallet WHERE chat_id=? AND user_id=?",
                (chat_id, uid),
            ) as c:
                row = await c.fetchone()
            family = row[0] if row else 0
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
        add_mora, add_to_treasury, get_bond_prices, get_user_bonds, sell_bonds,
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

    ok, _ = await sell_bonds(uid, chat_id, bond_key, amount)
    if not ok:
        raise ValueError("Не удалось оформить продажу")

    new_balance = await add_mora(uid, chat_id, net_revenue)
    if bond_tax > 0:
        await add_to_treasury(chat_id, bond_tax, "bonds", uid)

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
