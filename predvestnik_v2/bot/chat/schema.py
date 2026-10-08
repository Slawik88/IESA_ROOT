"""Расширения схемы БД для нового чат-бота. Только добавление колонок и таблиц:
существующие данные не меняются и не удаляются."""
from __future__ import annotations

from infrastructure.database import get_pool
from infrastructure.pg_adapter import PGAdapter

STATEMENTS = (
    # Новая шкала из 10 локальных рангов, начата с нуля. Старая колонка
    # local_rank сохраняется в БД, но не читается; NULL = «Участник».
    "ALTER TABLE user_chat_stats ADD COLUMN IF NOT EXISTS chat_rank SMALLINT",
    # Единственный владелец чата, синхронизируется с Telegram.
    "ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS owner_id BIGINT",
    # Снятие варна сохраняет историю: строка остаётся, ставится отметка.
    "ALTER TABLE user_warnings ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMP",
    "ALTER TABLE user_warnings ADD COLUMN IF NOT EXISTS revoked_by BIGINT",
    "CREATE INDEX IF NOT EXISTS idx_user_warnings_active ON user_warnings (chat_id, user_id) WHERE revoked_at IS NULL",
    # Срочный бан: после expires_at запись в чёрном списке перестаёт действовать.
    "ALTER TABLE chat_blacklist ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP",
    # Закрытый чат: пишут только ранги с правом write_closed.
    "ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS is_closed BOOLEAN DEFAULT FALSE",
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
