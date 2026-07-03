"""
infrastructure/repositories/wallet_log.py
All wallet_log DB operations. No business logic.
"""
import aiosqlite

# БЛОК 36.2-фикс: фильтр «гача» матчил только вымершие 4-тирные source (после
# Block 8 реальные — gacha_mora/gacha_diamond/gacha_drop) и не показывал ни одной
# современной транзакции. Legacy-ключи оставлены для старых записей в логе.
_GACHA_SOURCES = ["gacha_mora", "gacha_diamond", "gacha_drop",
                  "gacha_novice", "gacha_standard", "gacha_premium"]
_AUCTION_SOURCES = ["auction_sale", "auction_buy", "auction_reserve", "auction_listing_fee"]
_SOURCE_FILTER_MAP: dict[str, list[str]] = {
    "гача":    _GACHA_SOURCES,
    "gacha":   _GACHA_SOURCES,
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
    "аукцион": _AUCTION_SOURCES,
    "auction": _AUCTION_SOURCES,
}


async def log_wallet(
    db: aiosqlite.Connection,
    user_id: int,
    *,
    delta_mora: float = 0.0,
    delta_diamonds: float = 0.0,
    delta_zarniki: float = 0.0,
    source: str,
    chat_id: int | None = None,
    target_id: int | None = None,
    note: str | None = None,
) -> None:
    """Record a wallet change. Reads current balance from DB after the operation.
    Does NOT commit — the caller controls the transaction."""
    if delta_mora == 0.0 and delta_diamonds == 0.0 and delta_zarniki == 0.0:
        return

    async with db.execute(
        "SELECT user_balance_mora, user_balance_diamonds, "
        "COALESCE(user_balance_zarniki, 0) FROM users WHERE user_tg_id = ?",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    bal_mora      = row[0] if row else 0.0
    bal_dia       = row[1] if row else 0.0
    bal_zarniki  = row[2] if row else 0.0

    await db.execute(
        """INSERT INTO wallet_log
            (user_id, chat_id, delta_mora, delta_diamonds, delta_zarniki,
             balance_mora_after, balance_diamonds_after, balance_zarniki_after,
             source, target_id, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, chat_id, delta_mora, delta_diamonds, delta_zarniki,
         bal_mora, bal_dia, bal_zarniki, source, target_id, note),
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
        "COALESCE(delta_zarniki, 0) AS delta_zarniki, "
        "balance_mora_after, balance_diamonds_after, "
        "COALESCE(balance_zarniki_after, 0) AS balance_zarniki_after, "
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
