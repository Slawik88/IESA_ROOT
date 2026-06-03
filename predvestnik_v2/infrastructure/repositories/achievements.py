import aiosqlite


async def get_achievement(db: aiosqlite.Connection, user_id: int, achievement_id: str) -> dict | None:
    async with db.execute(
        "SELECT level, progress FROM achievements WHERE user_id = ? AND achievement_id = ?",
        (user_id, achievement_id),
    ) as c:
        row = await c.fetchone()
    if not row:
        return None
    return {"level": row[0], "progress": row[1]}


async def get_all_achievements(db: aiosqlite.Connection, user_id: int) -> dict:
    """Return {achievement_id: {level, progress}} for all achievements the user has."""
    async with db.execute(
        "SELECT achievement_id, level, progress FROM achievements WHERE user_id = ?",
        (user_id,),
    ) as c:
        rows = await c.fetchall()
    return {r[0]: {"level": r[1], "progress": r[2]} for r in rows}


async def get_user_achievements_count(db, user_id: int) -> int:
    """Count achievements the user has unlocked (level > 0)."""
    async with db.execute(
        "SELECT COUNT(*) FROM achievements WHERE user_id = ? AND level > 0",
        (user_id,),
    ) as c:
        row = await c.fetchone()
    return int(row[0]) if row else 0


async def upsert_achievement(
    db: aiosqlite.Connection,
    user_id: int,
    achievement_id: str,
    level: int,
    progress: float,
) -> None:
    """Upsert achievement record. No commit."""
    await db.execute(
        """INSERT INTO achievements (user_id, achievement_id, level, progress)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(user_id, achievement_id) DO UPDATE SET
               level = excluded.level,
               progress = excluded.progress,
               updated_at = CURRENT_TIMESTAMP""",
        (user_id, achievement_id, level, progress),
    )
