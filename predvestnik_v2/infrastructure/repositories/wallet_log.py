"""
infrastructure/repositories/wallet_log.py
All wallet_log DB operations. No business logic.
"""
import aiosqlite

_SOURCE_FILTER_MAP: dict[str, list[str]] = {
    "гача":    ["gacha_novice", "gacha_standard", "gacha_premium", "gacha_diamond"],
    "gacha":   ["gacha_novice", "gacha_standard", "gacha_premium", "gacha_diamond"],
    "переводы": ["transfer_in", "transfer_out"],
    "transfers": ["transfer_in", "transfer_out"],
    "магазин": ["shop_purchase", "daily_deal_purchase"],
    "shop":    ["shop_purchase", "daily_deal_purchase"],
    "стрик":   ["streak_daily", "streak_block_end", "streak_recovery"],
    "streak":  ["streak_daily", "streak_block_end", "streak_recovery"],
    "игры":    ["gamble_win", "gamble_loss"],
    "games":   ["gamble_win", "gamble_loss"],
    "походы":  ["expedition"],
    "expedition": ["expedition"],
    "аукцион": ["auction_sale", "auction_buy", "auction_reserve"],
    "auction": ["auction_sale", "auction_buy", "auction_reserve"],
}


async def log_wallet(
    db: aiosqlite.Connection,
    user_id: int,
    *,
    delta_mora: float = 0.0,
    delta_diamonds: float = 0.0,
    delta_crystals: float = 0.0,
    source: str,
    chat_id: int | None = None,
    target_id: int | None = None,
    note: str | None = None,
) -> None:
    """Record a wallet change. Reads current balance from DB after the operation.
    Does NOT commit — the caller controls the transaction."""
    if delta_mora == 0.0 and delta_diamonds == 0.0 and delta_crystals == 0.0:
        return

    async with db.execute(
        "SELECT user_balance_mora, user_balance_diamonds, "
        "COALESCE(user_balance_crystals, 0) FROM users WHERE user_tg_id = ?",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    bal_mora      = row[0] if row else 0.0
    bal_dia       = row[1] if row else 0.0
    bal_crystals  = row[2] if row else 0.0

    await db.execute(
        """INSERT INTO wallet_log
            (user_id, chat_id, delta_mora, delta_diamonds, delta_crystals,
             balance_mora_after, balance_diamonds_after, balance_crystals_after,
             source, target_id, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, chat_id, delta_mora, delta_diamonds, delta_crystals,
         bal_mora, bal_dia, bal_crystals, source, target_id, note),
    )


async def get_recent(
    db: aiosqlite.Connection,
    user_id: int,
    n: int = 20,
    filter_source: str | None = None,
) -> list[dict]:
    """Return up to n recent wallet entries. filter_source can be a human-readable
    category (e.g. 'гача', 'переводы') or a raw source string."""
    sources = None
    if filter_source:
        clean = filter_source.lower().strip()
        sources = _SOURCE_FILTER_MAP.get(clean, [clean])

    base_cols = (
        "id, delta_mora, delta_diamonds, "
        "COALESCE(delta_crystals, 0) AS delta_crystals, "
        "balance_mora_after, balance_diamonds_after, "
        "COALESCE(balance_crystals_after, 0) AS balance_crystals_after, "
        "source, target_id, note, created_at"
    )

    if sources:
        placeholders = ",".join("?" * len(sources))
        query = (
            f"SELECT {base_cols} FROM wallet_log "
            f"WHERE user_id = ? AND source IN ({placeholders}) "
            f"ORDER BY created_at DESC LIMIT ?"
        )
        params = (user_id, *sources, n)
    else:
        query = (
            f"SELECT {base_cols} FROM wallet_log "
            f"WHERE user_id = ? ORDER BY created_at DESC LIMIT ?"
        )
        params = (user_id, n)

    async with db.execute(query, params) as c:
        return [dict(r) for r in await c.fetchall()]
