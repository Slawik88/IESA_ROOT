"""Доступ к данным уведомлений в личку: согласия, настройки игрока и очередь сообщений.

Согласие хранится в user_notification_prefs (строка есть и enabled = TRUE). Нет строки = НЕ согласен:
в отличие от старого notifications.is_enabled, где отсутствие строки означало «включено».
"""
from __future__ import annotations

import json
from datetime import datetime

from core import dm_push as rules


async def _schema_ready(db) -> bool:
    async with db.execute(
        "SELECT to_regclass('dm_push_outbox') IS NOT NULL AND to_regclass('dm_push_settings') IS NOT NULL "
        "AND to_regclass('dm_push_topics') IS NOT NULL AND EXISTS (SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = 'dm_push_settings' AND column_name = 'next_check_at')"
    ) as c:
        row = await c.fetchone()
    return bool(row and row[0])


async def ensure_schema(db) -> None:
    """Таблицы очереди и настроек; повторный вызов ничего не меняет. Готовую схему проверяет один запрос без блокировок.
    Установка идёт под общим замком: бот при старте и первый запрос Mini App могут прийти одновременно, а параллельный DDL
    в PostgreSQL не сериализуется (на проде так падало «tuple concurrently updated», см. quests_v1)."""
    if await _schema_ready(db):
        return
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('ensure_schema:dm_push', 0))")
        if not await _schema_ready(db):
            await _install(db)


async def _install(db) -> None:
    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS dm_push_settings (
            user_id BIGINT PRIMARY KEY,
            dm_confirmed_at TIMESTAMPTZ,
            dm_disabled_at TIMESTAMPTZ,
            quiet_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            tz_offset SMALLINT NOT NULL DEFAULT {rules.DEFAULT_TZ_OFFSET} CHECK (tz_offset BETWEEN {rules.MIN_TZ} AND {rules.MAX_TZ}),
            unanswered SMALLINT NOT NULL DEFAULT 0,
            paused_at TIMESTAMPTZ,
            next_check_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    await db.execute("ALTER TABLE dm_push_settings ADD COLUMN IF NOT EXISTS next_check_at TIMESTAMPTZ")
    await db.execute("""
        CREATE TABLE IF NOT EXISTS dm_push_outbox (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            category TEXT NOT NULL,
            dedup_key TEXT NOT NULL,
            text TEXT NOT NULL,
            button JSONB,
            attempts SMALLINT NOT NULL DEFAULT 0,
            batch BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            sent_at TIMESTAMPTZ,
            dropped_at TIMESTAMPTZ,
            drop_reason TEXT,
            UNIQUE (user_id, dedup_key)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS dm_push_topics (
            user_id BIGINT NOT NULL,
            topic_key TEXT NOT NULL,
            thread_id BIGINT,
            failed_at TIMESTAMPTZ,
            PRIMARY KEY (user_id, topic_key)
        )
    """)
    # Таблицы только что созданы и пусты, поэтому обычный CREATE INDEX (без CONCURRENTLY) никого не блокирует.
    await db.execute("CREATE INDEX IF NOT EXISTS idx_dm_push_outbox_pending ON dm_push_outbox (user_id, created_at) "
                     "WHERE sent_at IS NULL AND dropped_at IS NULL")
    await db.execute("CREATE INDEX IF NOT EXISTS idx_dm_push_outbox_sent ON dm_push_outbox (user_id, sent_at) WHERE sent_at IS NOT NULL")


# ── согласия ────────────────────────────────────────────────────────────────

async def consented(db, user_id: int) -> set[str]:
    async with db.execute("SELECT category FROM user_notification_prefs WHERE user_id = ? AND enabled = TRUE", (int(user_id),)) as c:
        return {r[0] for r in await c.fetchall()}


async def has_consent(db, user_id: int, category: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM user_notification_prefs WHERE user_id = ? AND category = ? AND enabled = TRUE", (int(user_id), category),
    ) as c:
        return await c.fetchone() is not None


async def set_consent(db, user_id: int, category: str, enabled: bool) -> None:
    """Включить или выключить категорию. Выключение сразу снимает с очереди уже стоящие сообщения этой категории."""
    await db.execute(
        "INSERT INTO user_notification_prefs (user_id, category, enabled) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, category) DO UPDATE SET enabled = EXCLUDED.enabled",
        (int(user_id), category, bool(enabled)),
    )
    if enabled:   # включил сам — значит, читает: счётчик «без отклика», пауза и отсрочка сбрасываются
        await db.execute("UPDATE dm_push_settings SET unanswered = 0, paused_at = NULL, next_check_at = NULL, updated_at = NOW() "
                         "WHERE user_id = ?", (int(user_id),))
    else:
        await drop_pending(db, int(user_id), "revoked", category=category)
    await db.commit()


# ── настройки и связь с игроком ─────────────────────────────────────────────

async def get_settings(db, user_id: int) -> dict:
    async with db.execute(
        "SELECT dm_confirmed_at, dm_disabled_at, quiet_enabled, tz_offset, unanswered, paused_at "
        "FROM dm_push_settings WHERE user_id = ?", (int(user_id),),
    ) as c:
        row = await c.fetchone()
    if row is None:
        return {"dm_confirmed_at": None, "dm_disabled_at": None, "quiet_enabled": True,
                "tz_offset": rules.DEFAULT_TZ_OFFSET, "unanswered": 0, "paused_at": None}
    return {"dm_confirmed_at": row[0], "dm_disabled_at": row[1], "quiet_enabled": bool(row[2]),
            "tz_offset": int(row[3]), "unanswered": int(row[4]), "paused_at": row[5]}


async def touch_contact(db, user_id: int) -> bool:
    """Игрок написал боту в личку или нажал кнопку: личка подтверждена, «без отклика» обнуляется.
    Пишет в базу только когда что-то меняется (не на каждое сообщение). True — запись изменилась."""
    async with db.execute(
        """
        INSERT INTO dm_push_settings (user_id, dm_confirmed_at) VALUES (?, NOW())
        ON CONFLICT (user_id) DO UPDATE SET dm_confirmed_at = COALESCE(dm_push_settings.dm_confirmed_at, NOW()),
            dm_disabled_at = NULL, unanswered = 0, paused_at = NULL, next_check_at = NULL, updated_at = NOW()
        WHERE dm_push_settings.dm_confirmed_at IS NULL OR dm_push_settings.dm_disabled_at IS NOT NULL
           OR dm_push_settings.unanswered > 0 OR dm_push_settings.paused_at IS NOT NULL
           OR dm_push_settings.next_check_at IS NOT NULL
        RETURNING 1
        """, (int(user_id),),
    ) as c:
        return await c.fetchone() is not None


async def mark_unreachable(db, user_id: int) -> None:
    """Telegram не пускает сообщение (бот заблокирован): больше не пишем и убираем очередь."""
    await db.execute(
        "INSERT INTO dm_push_settings (user_id, dm_disabled_at) VALUES (?, NOW()) "
        "ON CONFLICT (user_id) DO UPDATE SET dm_disabled_at = NOW(), updated_at = NOW()", (int(user_id),),
    )
    await drop_pending(db, int(user_id), "unreachable")


async def set_quiet(db, user_id: int, enabled: bool) -> None:
    await db.execute(
        "INSERT INTO dm_push_settings (user_id, quiet_enabled) VALUES (?, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET quiet_enabled = EXCLUDED.quiet_enabled, next_check_at = NULL, updated_at = NOW()",
        (int(user_id), bool(enabled)),
    )
    await db.commit()


async def set_tz(db, user_id: int, offset: int) -> None:
    await db.execute(
        "INSERT INTO dm_push_settings (user_id, tz_offset) VALUES (?, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET tz_offset = EXCLUDED.tz_offset, next_check_at = NULL, updated_at = NOW()",
        (int(user_id), int(offset)),
    )
    await db.commit()


async def defer(db, user_id: int, until: datetime) -> None:
    """Этому игроку сейчас писать нельзя (ночь, лимит, пауза, сбой): в проходах доставки его нет до момента ``until``."""
    await db.execute(
        "INSERT INTO dm_push_settings (user_id, next_check_at) VALUES (?, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET next_check_at = EXCLUDED.next_check_at", (int(user_id), until),
    )


async def account_alive(db, user_id: int) -> bool:
    """Аккаунт не стоит на удалении. Игрока без записи в users (писал только боту) не отсекаем: писать ему можно."""
    async with db.execute("SELECT 1 FROM users WHERE user_tg_id = ? AND deleted_at IS NOT NULL", (int(user_id),)) as c:
        return await c.fetchone() is None


async def record_sent_to_player(db, user_id: int) -> int:
    """+1 к «сообщений без отклика». Достигнут предел — пауза до первого ответа игрока. Возвращает новое значение."""
    async with db.execute(
        "UPDATE dm_push_settings SET unanswered = unanswered + 1, "
        "paused_at = CASE WHEN unanswered + 1 >= ? THEN NOW() ELSE paused_at END, updated_at = NOW() "
        "WHERE user_id = ? RETURNING unanswered", (rules.UNANSWERED_LIMIT, int(user_id)),
    ) as c:
        row = await c.fetchone()
    return int(row[0]) if row else 0


# ── темы лички ──────────────────────────────────────────────────────────────

async def get_topic(db, user_id: int, topic_key: str) -> dict:
    async with db.execute("SELECT thread_id, failed_at FROM dm_push_topics WHERE user_id = ? AND topic_key = ?", (int(user_id), topic_key)) as c:
        row = await c.fetchone()
    return {"thread_id": int(row[0]) if row and row[0] is not None else None, "failed_at": row[1] if row else None}


async def save_topic(db, user_id: int, topic_key: str, thread_id: int) -> None:
    await db.execute(
        "INSERT INTO dm_push_topics (user_id, topic_key, thread_id, failed_at) VALUES (?, ?, ?, NULL) "
        "ON CONFLICT (user_id, topic_key) DO UPDATE SET thread_id = EXCLUDED.thread_id, failed_at = NULL",
        (int(user_id), topic_key, int(thread_id)),
    )


async def fail_topic(db, user_id: int, topic_key: str) -> None:
    """Тему создать или использовать не вышло: общий поток, новая попытка не раньше чем через TOPIC_RETRY."""
    await db.execute(
        "INSERT INTO dm_push_topics (user_id, topic_key, thread_id, failed_at) VALUES (?, ?, NULL, NOW()) "
        "ON CONFLICT (user_id, topic_key) DO UPDATE SET thread_id = NULL, failed_at = NOW()",
        (int(user_id), topic_key),
    )


# ── очередь ─────────────────────────────────────────────────────────────────

async def add(db, user_id: int, category: str, dedup_key: str, text: str, button: dict | None) -> int | None:
    """Поставить сообщение в очередь. None — такое событие уже было (dedup_key)."""
    async with db.execute(
        "INSERT INTO dm_push_outbox (user_id, category, dedup_key, text, button) VALUES (?, ?, ?, ?, ?::jsonb) "
        "ON CONFLICT (user_id, dedup_key) DO NOTHING RETURNING id",
        (int(user_id), category, dedup_key, text, json.dumps(button, ensure_ascii=False) if button else None),
    ) as c:
        row = await c.fetchone()
    return int(row[0]) if row else None


async def pending_user_ids(db, now: datetime, limit: int) -> list[int]:
    """Игроки, которым есть что отправить и у которых отсрочка (ночь, лимит, пауза, сбой) уже закончилась."""
    async with db.execute(
        "SELECT o.user_id FROM dm_push_outbox o LEFT JOIN dm_push_settings s ON s.user_id = o.user_id "
        "WHERE o.sent_at IS NULL AND o.dropped_at IS NULL AND (s.next_check_at IS NULL OR s.next_check_at <= ?) "
        "GROUP BY o.user_id ORDER BY MIN(o.created_at) LIMIT ?", (now, int(limit)),
    ) as c:
        return [int(r[0]) for r in await c.fetchall()]


async def pending_rows(db, user_id: int) -> list[dict]:
    async with db.execute(
        "SELECT id, category, dedup_key, text, button, attempts, created_at FROM dm_push_outbox "
        "WHERE user_id = ? AND sent_at IS NULL AND dropped_at IS NULL ORDER BY created_at, id", (int(user_id),),
    ) as c:
        rows = await c.fetchall()
    return [{"id": int(r[0]), "category": r[1], "dedup_key": r[2], "text": r[3], "button": _json(r[4]),
             "attempts": int(r[5]), "created_at": r[6]} for r in rows]


def _json(value):
    """jsonb приходит из asyncpg строкой (кодека в пуле нет): без разбора кнопка не получилась бы никогда."""
    if isinstance(value, str):
        return json.loads(value)
    return value


async def sent_batches_since(db, user_id: int, since: datetime) -> int:
    """Сколько сообщений (дайджест = одно) ушло игроку с момента since."""
    async with db.execute(
        "SELECT COUNT(DISTINCT COALESCE(batch, id)) FROM dm_push_outbox WHERE user_id = ? AND sent_at IS NOT NULL AND sent_at > ?",
        (int(user_id), since),
    ) as c:
        row = await c.fetchone()
    return int(row[0] or 0)


async def mark_sent(db, ids: list[int]) -> None:
    if ids:
        await db.execute("UPDATE dm_push_outbox SET sent_at = NOW(), batch = ? WHERE id = ANY(?::bigint[])", (min(ids), list(ids)))


async def mark_failed(db, ids: list[int], max_attempts: int) -> None:
    """Неудачная отправка: +1 к попыткам; исчерпал — убираем, чтобы не крутилась вечно."""
    if not ids:
        return
    await db.execute("UPDATE dm_push_outbox SET attempts = attempts + 1 WHERE id = ANY(?::bigint[])", (list(ids),))
    await db.execute(
        "UPDATE dm_push_outbox SET dropped_at = NOW(), drop_reason = 'failed' "
        "WHERE id = ANY(?::bigint[]) AND attempts >= ? AND sent_at IS NULL", (list(ids), int(max_attempts)),
    )


async def drop(db, ids: list[int], reason: str) -> None:
    if ids:
        await db.execute("UPDATE dm_push_outbox SET dropped_at = NOW(), drop_reason = ? WHERE id = ANY(?::bigint[]) AND sent_at IS NULL",
                         (reason, list(ids)))


async def drop_pending_key(db, user_id: int, dedup_key: str, reason: str) -> None:
    """Withdraw one not yet sent message (the event it announced was cancelled)."""
    await db.execute("UPDATE dm_push_outbox SET dropped_at = NOW(), drop_reason = ? WHERE user_id = ? AND dedup_key = ? "
                     "AND sent_at IS NULL AND dropped_at IS NULL", (reason, int(user_id), dedup_key))


async def drop_pending(db, user_id: int, reason: str, *, category: str | None = None) -> None:
    sql = "UPDATE dm_push_outbox SET dropped_at = NOW(), drop_reason = ? WHERE user_id = ? AND sent_at IS NULL AND dropped_at IS NULL"
    args: list = [reason, int(user_id)]
    if category:
        sql += " AND category = ?"
        args.append(category)
    await db.execute(sql, tuple(args))


async def gc(db, older_than_days: int = 30) -> None:
    """Старые отправленные и снятые строки не нужны: только очередь и счётчик за сутки."""
    await db.execute(
        "DELETE FROM dm_push_outbox WHERE COALESCE(sent_at, dropped_at) < NOW() - make_interval(days => ?)", (int(older_than_days),),
    )
