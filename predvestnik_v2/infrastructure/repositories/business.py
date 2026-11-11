"""Доступ к данным бота в личных переписках игрока (Telegram Business, S24).

Хранится только служебное: какая связь чья, есть ли право отвечать, в каких переписках игрок включил бота, номера уже
выполненных команд; с S29a — настройки функций, номера пультов, частота кнопок пульта и отказы собеседников
(«Не предлагать мне»). Текстов сообщений здесь нет ни в одной таблице.
"""
from __future__ import annotations


async def _ready(db) -> bool:
    async with db.execute("SELECT to_regclass('business_partner_optout') IS NOT NULL") as c:   # последняя по порядку (S29a)
        row = await c.fetchone()
    return bool(row and row[0])


async def ensure_schema(db) -> None:
    """Повторный вызов ничего не меняет; установка под общим замком (параллельный DDL в PostgreSQL не сериализуется)."""
    if await _ready(db):
        return
    async with db.connection.transaction():
        await db.execute("SELECT pg_advisory_xact_lock(hashtextextended('ensure_schema:business', 0))")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS business_connections (
                id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                user_chat_id BIGINT NOT NULL,
                can_reply BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_business_connections_user ON business_connections (user_id)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS business_chats (
                connection_id TEXT NOT NULL REFERENCES business_connections (id) ON DELETE CASCADE,
                chat_id BIGINT NOT NULL,
                enabled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (connection_id, chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS business_handled (
                connection_id TEXT NOT NULL REFERENCES business_connections (id) ON DELETE CASCADE,
                chat_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                handled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (connection_id, chat_id, message_id)
            )
        """)
        await db.execute("CREATE INDEX IF NOT EXISTS idx_business_handled_at ON business_handled (handled_at)")
        # S29a: настройки (общие и для одной переписки), пульты, частота кнопок, отказы собеседников
        await db.execute("""
            CREATE TABLE IF NOT EXISTS business_settings (
                user_id BIGINT NOT NULL,
                key TEXT NOT NULL,
                value BOOLEAN NOT NULL,
                PRIMARY KEY (user_id, key)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS business_chat_settings (
                connection_id TEXT NOT NULL REFERENCES business_connections (id) ON DELETE CASCADE,
                chat_id BIGINT NOT NULL,
                key TEXT NOT NULL,
                value BOOLEAN NOT NULL,
                PRIMARY KEY (connection_id, chat_id, key)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS business_remotes (
                id BIGSERIAL PRIMARY KEY,
                connection_id TEXT NOT NULL REFERENCES business_connections (id) ON DELETE CASCADE,
                chat_id BIGINT NOT NULL,
                partner_name TEXT NOT NULL DEFAULT '',
                UNIQUE (connection_id, chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS business_usage (
                user_id BIGINT NOT NULL,
                action TEXT NOT NULL,
                uses INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, action)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS business_partner_optout (
                user_id BIGINT PRIMARY KEY,
                at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)


async def save_connection(db, connection_id: str, user_id: int, user_chat_id: int, can_reply: bool) -> bool:
    """Записать живую связь. True — связь новая (раньше её не было)."""
    async with db.execute(
        "INSERT INTO business_connections (id, user_id, user_chat_id, can_reply) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (id) DO UPDATE SET user_id = EXCLUDED.user_id, user_chat_id = EXCLUDED.user_chat_id, "
        "can_reply = EXCLUDED.can_reply, updated_at = NOW() RETURNING (xmax = 0)",
        (str(connection_id), int(user_id), int(user_chat_id), bool(can_reply)),
    ) as c:
        row = await c.fetchone()
    return bool(row and row[0])


async def drop_connection(db, connection_id: str) -> bool:
    """Игрок отключил бота: связь и всё, что к ней относится (включённые переписки, номера команд), удаляется."""
    async with db.execute("DELETE FROM business_connections WHERE id = ? RETURNING id", (str(connection_id),)) as c:
        return await c.fetchone() is not None


async def connection(db, connection_id: str) -> dict | None:
    async with db.execute("SELECT id, user_id, user_chat_id, can_reply FROM business_connections WHERE id = ?",
                          (str(connection_id),)) as c:
        row = await c.fetchone()
    return {"id": row[0], "user_id": int(row[1]), "user_chat_id": int(row[2]), "can_reply": bool(row[3])} if row else None


async def chat_enabled(db, connection_id: str, chat_id: int) -> bool:
    async with db.execute("SELECT 1 FROM business_chats WHERE connection_id = ? AND chat_id = ?", (str(connection_id), int(chat_id))) as c:
        return await c.fetchone() is not None


async def set_chat(db, connection_id: str, chat_id: int, enabled: bool) -> bool:
    """Включить или выключить бота в одной переписке. True — состояние изменилось."""
    if enabled:
        sql = "INSERT INTO business_chats (connection_id, chat_id) VALUES (?, ?) ON CONFLICT DO NOTHING RETURNING chat_id"
    else:
        sql = "DELETE FROM business_chats WHERE connection_id = ? AND chat_id = ? RETURNING chat_id"
    async with db.execute(sql, (str(connection_id), int(chat_id))) as c:
        return await c.fetchone() is not None


async def mark_handled(db, connection_id: str, chat_id: int, message_id: int, keep_hours: int) -> bool:
    """Запомнить команду. False — эту команду уже выполняли (Telegram прислал то же обновление ещё раз)."""
    await db.execute("DELETE FROM business_handled WHERE handled_at < NOW() - make_interval(hours => ?)", (int(keep_hours),))
    async with db.execute(
        "INSERT INTO business_handled (connection_id, chat_id, message_id) VALUES (?, ?, ?) ON CONFLICT DO NOTHING RETURNING message_id",
        (str(connection_id), int(chat_id), int(message_id)),
    ) as c:
        return await c.fetchone() is not None


async def known_player(db, user_id: int) -> dict | None:
    """Игрок, которого бот знает (писал боту или в чате с ботом), и не стоящий на удалении."""
    async with db.execute("SELECT user_tg_username, deleted_at IS NOT NULL FROM users WHERE user_tg_id = ?", (int(user_id),)) as c:
        row = await c.fetchone()
    return {"username": row[0], "deleting": bool(row[1])} if row else None


# ── S29a: настройки, пульты, частота кнопок, отказы собеседников ─────────────

async def settings(db, user_id: int) -> dict[str, bool]:
    async with db.execute("SELECT key, value FROM business_settings WHERE user_id = ?", (int(user_id),)) as c:
        return {r[0]: bool(r[1]) for r in await c.fetchall()}


async def set_setting(db, user_id: int, key: str, value: bool) -> None:
    await db.execute("INSERT INTO business_settings (user_id, key, value) VALUES (?, ?, ?) "
                     "ON CONFLICT (user_id, key) DO UPDATE SET value = EXCLUDED.value", (int(user_id), key, bool(value)))


async def chat_settings(db, connection_id: str, chat_id: int) -> dict[str, bool]:
    async with db.execute("SELECT key, value FROM business_chat_settings WHERE connection_id = ? AND chat_id = ?",
                          (str(connection_id), int(chat_id))) as c:
        return {r[0]: bool(r[1]) for r in await c.fetchall()}


async def set_chat_setting(db, connection_id: str, chat_id: int, key: str, value: bool | None) -> None:
    """None — как в общих настройках (строка удаляется)."""
    if value is None:
        await db.execute("DELETE FROM business_chat_settings WHERE connection_id = ? AND chat_id = ? AND key = ?",
                         (str(connection_id), int(chat_id), key))
        return
    await db.execute("INSERT INTO business_chat_settings (connection_id, chat_id, key, value) VALUES (?, ?, ?, ?) "
                     "ON CONFLICT (connection_id, chat_id, key) DO UPDATE SET value = EXCLUDED.value",
                     (str(connection_id), int(chat_id), key, bool(value)))


async def remote_id(db, connection_id: str, chat_id: int, partner_name: str) -> int:
    """Короткий номер переписки для кнопок пульта (id связи в кнопку не помещается) и имя собеседника для заголовка пульта."""
    async with db.execute(
        "INSERT INTO business_remotes (connection_id, chat_id, partner_name) VALUES (?, ?, ?) "
        "ON CONFLICT (connection_id, chat_id) DO UPDATE SET partner_name = EXCLUDED.partner_name RETURNING id",
        (str(connection_id), int(chat_id), str(partner_name)[:64]),
    ) as c:
        return int((await c.fetchone())[0])


async def remote(db, remote_id_: int) -> dict | None:
    async with db.execute(
        "SELECT r.id, r.connection_id, r.chat_id, c.user_id, c.user_chat_id, c.can_reply, r.partner_name FROM business_remotes r "
        "JOIN business_connections c ON c.id = r.connection_id WHERE r.id = ?", (int(remote_id_),),
    ) as c:
        row = await c.fetchone()
    if not row:
        return None
    return {"remote_id": int(row[0]), "chat_id": int(row[2]), "partner_name": row[6] or "собеседник",
            "connection": {"id": row[1], "user_id": int(row[3]), "user_chat_id": int(row[4]), "can_reply": bool(row[5])}}


async def usage(db, user_id: int) -> dict[str, int]:
    async with db.execute("SELECT action, uses FROM business_usage WHERE user_id = ?", (int(user_id),)) as c:
        return {r[0]: int(r[1]) for r in await c.fetchall()}


async def count_use(db, user_id: int, action: str) -> None:
    await db.execute("INSERT INTO business_usage (user_id, action, uses) VALUES (?, ?, 1) "
                     "ON CONFLICT (user_id, action) DO UPDATE SET uses = business_usage.uses + 1", (int(user_id), action))


async def partner_opted_out(db, user_id: int) -> bool:
    async with db.execute("SELECT 1 FROM business_partner_optout WHERE user_id = ?", (int(user_id),)) as c:
        return await c.fetchone() is not None


async def set_partner_optout(db, user_id: int, opted_out: bool) -> bool:
    """True — состояние изменилось."""
    sql = ("INSERT INTO business_partner_optout (user_id) VALUES (?) ON CONFLICT DO NOTHING RETURNING user_id" if opted_out
           else "DELETE FROM business_partner_optout WHERE user_id = ? RETURNING user_id")
    async with db.execute(sql, (int(user_id),)) as c:
        return await c.fetchone() is not None
