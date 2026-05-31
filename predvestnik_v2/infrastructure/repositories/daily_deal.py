import aiosqlite


async def get_current_deals(db: aiosqlite.Connection) -> list[dict]:
    """Return all slots for today (up to 7). Empty list if not yet generated."""
    async with db.execute(
        "SELECT slot, item_id, quantity, price_mora, price_diamonds, generated_at "
        "FROM daily_deal_current ORDER BY slot ASC"
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_generated_at(db: aiosqlite.Connection) -> str | None:
    """Return the generated_at timestamp of the current batch (slot 1), or None."""
    async with db.execute(
        "SELECT generated_at FROM daily_deal_current WHERE slot = 1"
    ) as c:
        row = await c.fetchone()
    return row[0] if row else None


async def save_deals(
    db: aiosqlite.Connection,
    slots: list[dict],
    generated_at: str,
) -> None:
    """Replace all current deal slots with the new batch.
    `slots` is a list of dicts: {slot, item_id, quantity, price_mora, price_diamonds}.
    """
    await db.execute("DELETE FROM daily_deal_current")
    for s in slots:
        await db.execute(
            "INSERT INTO daily_deal_current (slot, item_id, quantity, price_mora, price_diamonds, generated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (s["slot"], s["item_id"], s["quantity"],
             s.get("price_mora", 0.0), s.get("price_diamonds", 0.0), generated_at),
        )
    await db.commit()


async def already_purchased(
    db: aiosqlite.Connection,
    user_id: int,
    slot: int,
    today: str,
) -> bool:
    async with db.execute(
        "SELECT 1 FROM daily_deal_purchases WHERE user_id = ? AND slot = ? AND purchase_date = ?",
        (user_id, slot, today),
    ) as c:
        return await c.fetchone() is not None


async def record_purchase(
    db: aiosqlite.Connection,
    user_id: int,
    slot: int,
    today: str,
) -> None:
    """Mark a slot as purchased for today. No commit."""
    await db.execute(
        "INSERT OR IGNORE INTO daily_deal_purchases (user_id, slot, purchase_date) VALUES (?, ?, ?)",
        (user_id, slot, today),
    )
