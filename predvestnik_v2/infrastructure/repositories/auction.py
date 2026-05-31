import aiosqlite
from datetime import datetime


async def create_lot(
    db: aiosqlite.Connection,
    seller_id: int,
    category: str,
    item_type: str,
    item_id_or_pet_id: int,
    quantity: int,
    item_name: str,
    min_bid: float,
    buyout: float | None,
    ends_at: str,
) -> int:
    async with db.execute(
        """INSERT INTO auction_lots
            (seller_id, category, item_type, item_id_or_pet_id, quantity,
             item_name, min_bid, buyout, ends_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id""",
        (seller_id, category, item_type, item_id_or_pet_id, quantity,
         item_name, min_bid, buyout, ends_at),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


async def get_lot(db: aiosqlite.Connection, lot_id: int) -> dict | None:
    async with db.execute("SELECT * FROM auction_lots WHERE id = ?", (lot_id,)) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_active_lots(
    db: aiosqlite.Connection,
    category: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[dict]:
    if category:
        q = "SELECT * FROM auction_lots WHERE status = 'active' AND category = ? ORDER BY ends_at ASC LIMIT ? OFFSET ?"
        p = (category, limit, offset)
    else:
        q = "SELECT * FROM auction_lots WHERE status = 'active' ORDER BY ends_at ASC LIMIT ? OFFSET ?"
        p = (limit, offset)
    async with db.execute(q, p) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_seller_active_lots(db: aiosqlite.Connection, seller_id: int) -> list[dict]:
    async with db.execute(
        "SELECT * FROM auction_lots WHERE seller_id = ? AND status = 'active' ORDER BY created_at DESC",
        (seller_id,),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def count_seller_active(db: aiosqlite.Connection, seller_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM auction_lots WHERE seller_id = ? AND status = 'active'",
        (seller_id,),
    ) as c:
        return (await c.fetchone())[0]


async def get_weekly_count(db: aiosqlite.Connection, seller_id: int, week_start: str) -> int:
    async with db.execute(
        "SELECT count FROM auction_weekly_count WHERE user_id = ? AND week_start = ?",
        (seller_id, week_start),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


async def incr_weekly_count(db: aiosqlite.Connection, seller_id: int, week_start: str) -> None:
    await db.execute(
        "INSERT INTO auction_weekly_count (user_id, week_start, count) VALUES (?, ?, 1) "
        "ON CONFLICT(user_id, week_start) DO UPDATE SET count = count + 1",
        (seller_id, week_start),
    )


async def update_lot_status(db: aiosqlite.Connection, lot_id: int, status: str) -> None:
    await db.execute("UPDATE auction_lots SET status = ? WHERE id = ?", (status, lot_id))


async def get_highest_bid(db: aiosqlite.Connection, lot_id: int) -> dict | None:
    async with db.execute(
        "SELECT * FROM auction_bids WHERE lot_id = ? AND is_active = 1 ORDER BY amount DESC LIMIT 1",
        (lot_id,),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_user_active_bid(db: aiosqlite.Connection, lot_id: int, bidder_id: int) -> dict | None:
    async with db.execute(
        "SELECT * FROM auction_bids WHERE lot_id = ? AND bidder_id = ? AND is_active = 1",
        (lot_id, bidder_id),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def deactivate_bid(db: aiosqlite.Connection, bid_id: int) -> None:
    await db.execute("UPDATE auction_bids SET is_active = 0 WHERE id = ?", (bid_id,))


async def insert_bid(
    db: aiosqlite.Connection, lot_id: int, bidder_id: int, amount: float
) -> int:
    async with db.execute(
        "INSERT INTO auction_bids (lot_id, bidder_id, amount) VALUES (?, ?, ?) RETURNING id",
        (lot_id, bidder_id, amount),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0


async def get_user_active_bids(db: aiosqlite.Connection, bidder_id: int) -> list[dict]:
    async with db.execute(
        "SELECT ab.*, al.item_name, al.ends_at, al.status as lot_status "
        "FROM auction_bids ab JOIN auction_lots al ON ab.lot_id = al.id "
        "WHERE ab.bidder_id = ? AND ab.is_active = 1 AND al.status = 'active' "
        "ORDER BY ab.placed_at DESC",
        (bidder_id,),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_expired_active_lots(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute(
        "SELECT * FROM auction_lots WHERE status = 'active' AND ends_at <= NOW()"
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_reserve(db: aiosqlite.Connection, user_id: int) -> float:
    async with db.execute(
        "SELECT reserved_mora FROM user_reserve WHERE user_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0.0


async def add_reserve(db: aiosqlite.Connection, user_id: int, amount: float) -> None:
    await db.execute(
        "INSERT INTO user_reserve (user_id, reserved_mora) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET reserved_mora = reserved_mora + ?",
        (user_id, amount, amount),
    )


async def remove_reserve(db: aiosqlite.Connection, user_id: int, amount: float) -> None:
    await db.execute(
        "UPDATE user_reserve SET reserved_mora = GREATEST(0, reserved_mora - ?) WHERE user_id = ?",
        (amount, user_id),
    )
