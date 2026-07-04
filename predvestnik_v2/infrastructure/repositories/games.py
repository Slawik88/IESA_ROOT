import aiosqlite

# R7: старое казино (get/set_cooldown) снесено. Дневной кап выигрыша
# (get/add_daily_winnings) остался — общий лимит с новыми скилл-играми
# (services/skill_games.py).


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
        "ON CONFLICT(user_id, date) DO UPDATE SET total_won = gamble_daily_winnings.total_won + ?",
        (user_id, date, amount, amount),
    )
