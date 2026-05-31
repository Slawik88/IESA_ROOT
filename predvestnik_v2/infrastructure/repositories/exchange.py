import aiosqlite


async def get_active_event(db: aiosqlite.Connection) -> dict | None:
    async with db.execute(
        "SELECT * FROM exchange_events WHERE status = 'active' LIMIT 1"
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_scheduled_event(db: aiosqlite.Connection) -> dict | None:
    async with db.execute(
        "SELECT * FROM exchange_events WHERE status = 'scheduled' ORDER BY starts_at LIMIT 1"
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def create_event(db: aiosqlite.Connection, starts_at: str, ends_at: str) -> int:
    cursor = await db.execute(
        "INSERT INTO exchange_events (starts_at, ends_at) VALUES (?, ?)",
        (starts_at, ends_at),
    )
    return cursor.lastrowid


async def activate_event(db: aiosqlite.Connection, event_id: int) -> None:
    await db.execute(
        "UPDATE exchange_events SET status = 'active' WHERE id = ?", (event_id,)
    )


async def finish_event(db: aiosqlite.Connection, event_id: int) -> None:
    await db.execute(
        "UPDATE exchange_events SET status = 'finished' WHERE id = ?", (event_id,)
    )


async def get_user_quota(db: aiosqlite.Connection, user_id: int, event_id: int) -> float:
    async with db.execute(
        "SELECT diamonds_converted FROM user_exchange_quota WHERE user_id = ? AND event_id = ?",
        (user_id, event_id),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0.0


async def add_quota(db: aiosqlite.Connection, user_id: int, event_id: int, amount: float) -> None:
    await db.execute(
        "INSERT INTO user_exchange_quota (user_id, event_id, diamonds_converted) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, event_id) DO UPDATE SET diamonds_converted = diamonds_converted + ?",
        (user_id, event_id, amount, amount),
    )
