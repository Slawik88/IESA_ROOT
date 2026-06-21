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
    """Атомарно увеличить прогресс (no-op если уже завершён). Возвращает новый
    прогресс или None, если квеста нет/он уже завершён. No commit.

    Аудит H5: атомарный инкремент `progress = progress + ?` (раньше был
    read-modify-write → потеря дельт при гонке бот+сайт)."""
    async with db.execute(
        "UPDATE daily_quests SET progress = progress + ? "
        "WHERE user_id = ? AND chat_id = ? AND date = ? AND quest_id = ? AND completed = 0 "
        "RETURNING progress",
        (delta, user_id, chat_id, date, quest_id),
    ) as c:
        row = await c.fetchone()
    return float(row[0]) if row else None


async def claim_once(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    date: str,
    quest_id: str,
) -> bool:
    """Атомарно «застолбить» одноразовое событие дня (напр. бонус за все квесты).
    Создаёт строку только при ПЕРВОМ вызове → возвращает True; при повторе строка
    уже есть (ON CONFLICT DO NOTHING) → False. Гард от двойной выдачи (БЛОК 5)."""
    async with db.execute(
        "INSERT INTO daily_quests (user_id, chat_id, date, quest_id, progress, completed) "
        "VALUES (?, ?, ?, ?, 1, 1) "
        "ON CONFLICT(user_id, chat_id, date, quest_id) DO NOTHING "
        "RETURNING quest_id",
        (user_id, chat_id, date, quest_id),
    ) as c:
        return (await c.fetchone()) is not None


async def mark_completed(
    db: aiosqlite.Connection,
    user_id: int,
    chat_id: int,
    date: str,
    quest_id: str,
) -> bool:
    """Атомарно пометить выполненным. Возвращает True ТОЛЬКО если этот вызов
    реально переключил 0→1 (аудит H5 — защита от двойной выдачи награды)."""
    async with db.execute(
        "UPDATE daily_quests SET completed = 1 "
        "WHERE user_id = ? AND chat_id = ? AND date = ? AND quest_id = ? AND completed = 0 "
        "RETURNING quest_id",
        (user_id, chat_id, date, quest_id),
    ) as c:
        return (await c.fetchone()) is not None
