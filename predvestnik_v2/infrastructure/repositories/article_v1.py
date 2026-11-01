"""«Моя статья»: выключатель чата, пауза и статья дня (S22).

Схема идемпотентна. Статья дня хранится в article_state: дата и индекс описания
повторного вызова в тот же день дают ту же статью. Таблица не переиспользует
ship_cooldowns: у функций разные паузы и будущие поля, а менять PK живой
таблицы S21 рискованно.
"""
from __future__ import annotations

MODULE_KEY = "module_article"

STATEMENTS = (
    "ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS module_article INTEGER DEFAULT 1",
    """CREATE TABLE IF NOT EXISTS article_state (
        chat_id    BIGINT NOT NULL,
        user_tg_id BIGINT NOT NULL DEFAULT 0,
        last_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        day        DATE,
        article_key TEXT,
        PRIMARY KEY (chat_id, user_tg_id)
    )""",
)


async def ensure_tables(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


async def chat_enabled(db, chat_id: int) -> bool:
    """Выключатель чата («бот статья выкл») и глобальный; оба по умолчанию включены."""
    if int(chat_id) < 0:
        async with db.execute("SELECT COALESCE(module_article, 1) FROM chat_settings WHERE chat_id = ?", (int(chat_id),)) as cur:
            row = await cur.fetchone()
        if row is not None and int(row[0]) == 0:
            return False
    async with db.execute("SELECT enabled FROM global_module_toggles WHERE module_key = ?", (MODULE_KEY,)) as cur:
        row = await cur.fetchone()
    return row is None or bool(row[0])


async def _pause_left(db, chat_id: int, user_tg_id: int, seconds: int) -> int:
    async with db.execute(
        "SELECT EXTRACT(EPOCH FROM (last_at + make_interval(secs => ?) - NOW())) FROM article_state "
        "WHERE chat_id = ? AND user_tg_id = ?",
        (int(seconds), int(chat_id), int(user_tg_id))) as cur:
        row = await cur.fetchone()
    return max(0, int(row[0])) if row and row[0] is not None else 0


async def pause_left(db, chat_id: int, user_id: int) -> int:
    """Самая долгая из двух пауз: игрока (article_state.user_tg_id) и чата (user_tg_id = 0)."""
    from core import article
    user_left = await _pause_left(db, chat_id, user_id, article.COOLDOWN_USER_SECONDS)
    chat_left = await _pause_left(db, chat_id, 0, article.COOLDOWN_CHAT_SECONDS)
    return max(user_left, chat_left)


async def today_key(db, chat_id: int, user_id: int, today) -> str | None:
    """Индекс описания статьи, выписанной этому игроку в этом чате сегодня (или None).

    today — объект date (asyncpg строг к типам колонок DATE)."""
    async with db.execute(
        "SELECT article_key FROM article_state WHERE chat_id = ? AND user_tg_id = ? AND day = ?::date",
        (int(chat_id), int(user_id), today)) as cur:
        row = await cur.fetchone()
    return str(row[0]) if row and row[0] is not None else None


async def remember(db, chat_id: int, user_id: int, article_key: str, today) -> None:
    """Отметить выдачу статьи: строка игрока хранит статью дня, строка чата только паузу."""
    await db.execute(
        "INSERT INTO article_state (chat_id, user_tg_id, last_at, day, article_key) VALUES (?, ?, NOW(), ?::date, ?) "
        "ON CONFLICT (chat_id, user_tg_id) DO UPDATE SET last_at = NOW(), day = EXCLUDED.day, "
        "article_key = EXCLUDED.article_key",
        (int(chat_id), int(user_id), today, str(article_key)))
    await db.execute(
        "INSERT INTO article_state (chat_id, user_tg_id, last_at) VALUES (?, 0, NOW()) "
        "ON CONFLICT (chat_id, user_tg_id) DO UPDATE SET last_at = NOW()",
        (int(chat_id),))
