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
    # Чистка: норма игрока с поправкой на мут и дату входа в чат.
    "ALTER TABLE purge_targets ADD COLUMN IF NOT EXISTS required_norm INTEGER",
    # Глобальная роль в боте (новая шкала, с нуля). Старая колонка global_rank не читается.
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_rank SMALLINT DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_sponsor BOOLEAN DEFAULT FALSE",
    # Настройки бота, которые меняет владелец бота (например, валюты для переводов).
    """CREATE TABLE IF NOT EXISTS bot_settings (
        key        TEXT PRIMARY KEY,
        value      TEXT NOT NULL,
        updated_by BIGINT,
        updated_at TIMESTAMPTZ DEFAULT NOW()
    )""",
    # Лучший стрик за всё время (текущий хранится в daily_login.streak, строка chat_id = 0).
    "ALTER TABLE daily_login ADD COLUMN IF NOT EXISTS best_streak INTEGER DEFAULT 0",
    # Согласие игрока на 18+ варп-команды в свой адрес (по умолчанию выключено).
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS allow_adult_warps BOOLEAN DEFAULT FALSE",
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
        from infrastructure.repositories import mafia_v1
        await mafia_v1.ensure_tables(db)   # ворота сообщений Мафии читают их в каждом сообщении
        from bot.chat.family import ensure_family_schema
        try:
            await ensure_family_schema(db)
        except Exception as exc:   # семья не должна мешать запуску остального бота
            from loguru import logger
            logger.exception(f"family schema failed: {exc}")
        commit = getattr(db, "commit", None)
        if commit:
            await commit()
