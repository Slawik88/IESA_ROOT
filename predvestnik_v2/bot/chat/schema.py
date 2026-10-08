"""Расширения схемы БД для нового чат-бота. Только добавление колонок и таблиц:
существующие данные не меняются и не удаляются."""
from __future__ import annotations

from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter

STATEMENTS = (
    # Новая шкала из 10 локальных рангов. Старая колонка local_rank не трогается;
    # NULL значит «ещё не переведён» — ранг выводится из local_rank (ranks.legacy_rank).
    "ALTER TABLE user_chat_stats ADD COLUMN IF NOT EXISTS chat_rank SMALLINT",
    # Единственный владелец чата, синхронизируется с Telegram.
    "ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS owner_id BIGINT",
    # Какой минимальный ранг нужен для действия в конкретном чате.
    """CREATE TABLE IF NOT EXISTS chat_rank_rights (
        chat_id    BIGINT   NOT NULL,
        action     TEXT     NOT NULL,
        min_rank   SMALLINT NOT NULL,
        updated_by BIGINT,
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (chat_id, action)
    )""",
)


async def ensure_chat_schema() -> None:
    async with get_pool().acquire() as conn:
        db = PGAdapter(conn)
        for sql in STATEMENTS:
            await db.execute(sql)
        commit = getattr(db, "commit", None)
        if commit:
            await commit()
