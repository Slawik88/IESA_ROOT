"""
infrastructure/schema.py
Схема БД «Домового». DDL идемпотентный: выполняется при каждом старте.

Соглашения: даты — TEXT 'YYYY-MM-DD' (наивные, час дома применяется сервисом),
метки времени — TEXT UTC 'YYYY-MM-DD HH:MM:SS', деньги — INTEGER копейки,
bool — INTEGER 0/1. Миграции появятся вместе с продом (schema_meta.version).
"""
import re

from loguru import logger

from infrastructure.db import db

_STATEMENTS = (
    # Пользователи: связка с Telegram; active_house_id — выбранный дом
    # (без FK: дом и пользователь создаются в разном порядке, живёт в сервисе)
    """
    CREATE TABLE IF NOT EXISTS users (
        tg_id           INTEGER PRIMARY KEY,
        first_name      TEXT NOT NULL,
        username        TEXT,
        active_house_id INTEGER,
        created_at      TEXT NOT NULL
    )
    """,
    # Дома: изолированные пространства
    """
    CREATE TABLE IF NOT EXISTS houses (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT NOT NULL,
        invite_token  TEXT NOT NULL UNIQUE,
        chat_id       INTEGER,
        created_by    INTEGER NOT NULL REFERENCES users(tg_id),
        created_at    TEXT NOT NULL
    )
    """,
    # Участие: человек × дом, роль и отображаемое имя
    """
    CREATE TABLE IF NOT EXISTS memberships (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        house_id     INTEGER NOT NULL REFERENCES houses(id),
        tg_id        INTEGER NOT NULL REFERENCES users(tg_id),
        display_name TEXT NOT NULL,
        role         TEXT NOT NULL DEFAULT 'member',
        status       TEXT NOT NULL DEFAULT 'active',
        joined_at    TEXT NOT NULL,
        UNIQUE (house_id, tg_id)
    )
    """,
    # Права участников (владельцу не нужны — у него всё и так)
    """
    CREATE TABLE IF NOT EXISTS member_permissions (
        house_id   INTEGER NOT NULL REFERENCES houses(id),
        tg_id      INTEGER NOT NULL REFERENCES users(tg_id),
        permission TEXT NOT NULL,
        UNIQUE (house_id, tg_id, permission)
    )
    """,
    # Версии графика: weekday_map — JSON {"<tg_id>": 0..6 или null}
    """
    CREATE TABLE IF NOT EXISTS schedule_versions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        house_id     INTEGER NOT NULL REFERENCES houses(id),
        weekday_map  TEXT NOT NULL,
        active_from  TEXT NOT NULL,
        created_at   TEXT NOT NULL
    )
    """,
    # Дни уборки: план (из версии графика) + факт
    """
    CREATE TABLE IF NOT EXISTS cleaning_days (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        house_id     INTEGER NOT NULL REFERENCES houses(id),
        tg_id        INTEGER NOT NULL REFERENCES users(tg_id),
        planned_date TEXT NOT NULL,
        status       TEXT NOT NULL DEFAULT 'open',  -- open | done | canceled
        actual_date  TEXT,
        closed_by    INTEGER,
        closed_at    TEXT,
        UNIQUE (house_id, planned_date, tg_id)
    )
    """,
    # Категории трат: сидятся дефолтом при создании дома, дополняются жильцами
    """
    CREATE TABLE IF NOT EXISTS categories (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        house_id   INTEGER NOT NULL REFERENCES houses(id),
        name       TEXT NOT NULL,
        is_default INTEGER NOT NULL DEFAULT 0,
        sort       INTEGER NOT NULL DEFAULT 0,
        UNIQUE (house_id, name)
    )
    """,
    # Взносы: заявлен жильцом → подтверждён владельцем (если включено подтверждение)
    """
    CREATE TABLE IF NOT EXISTS contributions (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        house_id     INTEGER NOT NULL REFERENCES houses(id),
        tg_id        INTEGER NOT NULL REFERENCES users(tg_id),
        amount_kop   INTEGER NOT NULL,
        month        TEXT NOT NULL,                -- 'YYYY-MM', к какому месяцу взнос
        status       TEXT NOT NULL DEFAULT 'declared',  -- declared | confirmed | rejected
        declared_at  TEXT NOT NULL,
        paid_on      TEXT,
        confirmed_by INTEGER,
        confirmed_at TEXT
    )
    """,
    # Траты: mode = house (из котла) | personal (за свои, ждёт возврата из котла)
    """
    CREATE TABLE IF NOT EXISTS expenses (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        house_id     INTEGER NOT NULL REFERENCES houses(id),
        tg_id        INTEGER NOT NULL REFERENCES users(tg_id),
        amount_kop   INTEGER NOT NULL,
        category_id  INTEGER REFERENCES categories(id),
        spent_on     TEXT NOT NULL,
        mode         TEXT NOT NULL DEFAULT 'house',
        reimbursed   INTEGER NOT NULL DEFAULT 0,
        description  TEXT NOT NULL DEFAULT '',
        created_at   TEXT NOT NULL
    )
    """,
    # Фото-чеки траты (1..N)
    """
    CREATE TABLE IF NOT EXISTS expense_photos (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_id INTEGER NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
        file_id    TEXT NOT NULL,
        local_path TEXT
    )
    """,
    # Настройки домов: ключи из core/settings_registry.HOUSE_SETTINGS
    """
    CREATE TABLE IF NOT EXISTS house_settings (
        house_id INTEGER NOT NULL REFERENCES houses(id),
        key      TEXT NOT NULL,
        value    TEXT NOT NULL,
        UNIQUE (house_id, key)
    )
    """,
    # Персональные уведомления: ключи из core/settings_registry.NOTIFY_SETTINGS
    """
    CREATE TABLE IF NOT EXISTS user_notify_settings (
        house_id INTEGER NOT NULL REFERENCES houses(id),
        tg_id    INTEGER NOT NULL REFERENCES users(tg_id),
        key      TEXT NOT NULL,
        value    TEXT NOT NULL,
        UNIQUE (house_id, tg_id, key)
    )
    """,
    # Изменение траты сохраняет исходные поля и автора правки.
    """
    CREATE TABLE IF NOT EXISTS expense_edits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        house_id INTEGER NOT NULL REFERENCES houses(id),
        expense_id BIGINT NOT NULL REFERENCES expenses(id) ON DELETE CASCADE,
        actor BIGINT NOT NULL,
        changed_at TEXT NOT NULL,
        before_json TEXT NOT NULL,
        after_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS money_import_items (
        house_id INTEGER NOT NULL REFERENCES houses(id),
        source_key TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        imported_by BIGINT NOT NULL,
        imported_at TEXT NOT NULL,
        kind TEXT NOT NULL,
        target_id BIGINT,
        UNIQUE (house_id, source_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS scheduler_log (
        house_id  INTEGER NOT NULL REFERENCES houses(id),
        event_key TEXT NOT NULL,
        day       TEXT NOT NULL,
        sent_at   TEXT NOT NULL,
        UNIQUE (house_id, event_key, day)
    )
    """,
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_days_house_date ON cleaning_days(house_id, planned_date)",
    "CREATE INDEX IF NOT EXISTS idx_days_open ON cleaning_days(status, planned_date)",
    "CREATE INDEX IF NOT EXISTS idx_expenses_house ON expenses(house_id, spent_on)",
    "CREATE INDEX IF NOT EXISTS idx_contrib_house ON contributions(house_id, month)",
)


_PG_TELEGRAM_COLUMNS = {
    "users": ("tg_id",),
    "houses": ("chat_id", "created_by"),
    "memberships": ("tg_id",),
    "member_permissions": ("tg_id",),
    "cleaning_days": ("tg_id", "closed_by"),
    "contributions": ("tg_id", "confirmed_by"),
    "expenses": ("tg_id",),
}


def _pg_statement(statement: str) -> str:
    """SQLite-DDL → PostgreSQL: автоинкремент и 64-битные Telegram ID."""
    statement = statement.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")
    return re.sub(
        r"\b(tg_id|chat_id|created_by|closed_by|confirmed_by)(\s+)INTEGER\b",
        r"\1\2BIGINT", statement,
    )


async def _upgrade_telegram_ids(conn) -> None:
    """Существующие таблицы тоже должны принимать ID групп и новых аккаунтов."""
    columns = await conn.fetch(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND data_type = 'integer'",
    )
    for row in columns:
        table, column = row["table_name"], row["column_name"]
        if column in _PG_TELEGRAM_COLUMNS.get(table, ()):
            # Идентификаторы разрешены только закрытым реестром выше.
            await conn.execute(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE BIGINT')


async def ensure_schema() -> None:
    async with db.acquire() as conn:
        for statement in _STATEMENTS:
            await conn.execute(_pg_statement(statement) if db.is_postgres else statement)
        if db.is_postgres:
            await _upgrade_telegram_ids(conn)
            await conn.execute("ALTER TABLE contributions ADD COLUMN IF NOT EXISTS paid_on TEXT")
        else:
            columns = await conn.fetch("PRAGMA table_info(contributions)")
            if not any(row["name"] == "paid_on" for row in columns):
                await conn.execute("ALTER TABLE contributions ADD COLUMN paid_on TEXT")
        await conn.execute("UPDATE contributions SET paid_on = SUBSTR(declared_at, 1, 10) WHERE paid_on IS NULL")
        for index in _INDEXES:
            await conn.execute(index)
    logger.info("🗄️ Схема «Домового» готова")
