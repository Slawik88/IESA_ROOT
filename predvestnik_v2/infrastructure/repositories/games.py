import aiosqlite
from datetime import datetime


async def get_cooldown(db: aiosqlite.Connection, user_id: int, game: str) -> str | None:
    async with db.execute(
        "SELECT last_played FROM gamble_cooldowns WHERE user_id = ? AND game = ?",
        (user_id, game),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else None


async def set_cooldown(db: aiosqlite.Connection, user_id: int, game: str) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "INSERT INTO gamble_cooldowns (user_id, game, last_played) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, game) DO UPDATE SET last_played = excluded.last_played",
        (user_id, game, now),
    )


async def get_daily_winnings(db: aiosqlite.Connection, user_id: int, date: str) -> float:
    async with db.execute(
        "SELECT total_won FROM gamble_daily_winnings WHERE user_id = ? AND date = ?",
        (user_id, date),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else 0.0


async def add_daily_winnings(
    db: aiosqlite.Connection, user_id: int, date: str, amount: float
) -> None:
    await db.execute(
        "INSERT INTO gamble_daily_winnings (user_id, date, total_won) VALUES (?, ?, ?) "
        "ON CONFLICT(user_id, date) DO UPDATE SET total_won = total_won + ?",
        (user_id, date, amount, amount),
    )
