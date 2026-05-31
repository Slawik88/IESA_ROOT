import aiosqlite


async def get_quest(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    date: str,
    quest_id: str,
) -> dict | None:
    async with db.execute(
        "SELECT quest_id, progress, completed FROM daily_quests "
        "WHERE user_id = ? AND chat_id = ? AND date = ? AND quest_id = ?",
        (user_id, chat_id, date, quest_id),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def get_user_quests(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    date: str,
) -> list[dict]:
    async with db.execute(
        "SELECT quest_id, progress, completed FROM daily_quests "
        "WHERE user_id = ? AND chat_id = ? AND date = ?",
        (user_id, chat_id, date),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def upsert_quest(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    date: str,
    quest_id: str,
    progress: float = 0.0,
    completed: int = 0,
) -> None:
    await db.execute(
        """INSERT INTO daily_quests (user_id, chat_id, date, quest_id, progress, completed)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(user_id, chat_id, date, quest_id) DO UPDATE SET
               progress = excluded.progress,
               completed = excluded.completed""",
        (user_id, chat_id, date, quest_id, progress, completed),
    )


async def increment_quest_progress(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    date: str,
    quest_id: str,
    delta: float,
) -> float:
    """Increment progress (no-op if already completed). Returns new progress. No commit."""
    existing = await get_quest(db, user_id, chat_id, date, quest_id)
    if not existing or existing["completed"]:
        return existing["progress"] if existing else 0.0
    new_progress = existing["progress"] + delta
    await db.execute(
        "UPDATE daily_quests SET progress = ? WHERE user_id = ? AND chat_id = ? AND date = ? AND quest_id = ?",
        (new_progress, user_id, chat_id, date, quest_id),
    )
    return new_progress


async def mark_completed(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    date: str,
    quest_id: str,
) -> None:
    await db.execute(
        "UPDATE daily_quests SET completed = 1 WHERE user_id = ? AND chat_id = ? AND date = ? AND quest_id = ?",
        (user_id, chat_id, date, quest_id),
    )
