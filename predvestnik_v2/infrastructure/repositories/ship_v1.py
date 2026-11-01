"""«Шипперим»: личный отказ, паузы между шиппингами и память последних пар (S21).

Схема идемпотентна: повторный ensure_tables ничего не меняет. Пауза хранится
двумя строками ship_cooldowns: строка игрока и строка чата (user_tg_id = 0).
Последние пары живут сутки и чистятся при каждой записи — таблица не растёт.
"""
from __future__ import annotations

MODULE_KEY = "module_ship"

STATEMENTS = (
    "ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS module_ship INTEGER DEFAULT 1",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS ship_opt_out BOOLEAN DEFAULT FALSE",
    """CREATE TABLE IF NOT EXISTS ship_cooldowns (
        chat_id    BIGINT NOT NULL,
        user_tg_id BIGINT NOT NULL DEFAULT 0,
        last_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (chat_id, user_tg_id)
    )""",
    """CREATE TABLE IF NOT EXISTS ship_recent_pairs (
        chat_id    BIGINT NOT NULL,
        user_a     BIGINT NOT NULL,
        user_b     BIGINT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (chat_id, user_a, user_b)
    )""",
)


async def ensure_tables(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


async def chat_enabled(db, chat_id: int) -> bool:
    """Выключатель чата («бот шипирить выкл») и глобальный; оба по умолчанию включены."""
    if int(chat_id) < 0:
        async with db.execute("SELECT COALESCE(module_ship, 1) FROM chat_settings WHERE chat_id = ?", (int(chat_id),)) as cur:
            row = await cur.fetchone()
        if row is not None and int(row[0]) == 0:
            return False
    async with db.execute("SELECT enabled FROM global_module_toggles WHERE module_key = ?", (MODULE_KEY,)) as cur:
        row = await cur.fetchone()
    return row is None or bool(row[0])


async def set_opt_out(db, user_id: int, opt_out: bool) -> None:
    """Личный отказ: игрок просил не выбирать его в пары (по образцу allow_adult_warps)."""
    await db.execute(
        "INSERT INTO users (user_tg_id, ship_opt_out) VALUES (?, ?) "
        "ON CONFLICT (user_tg_id) DO UPDATE SET ship_opt_out = EXCLUDED.ship_opt_out",
        (int(user_id), bool(opt_out)))


async def opted_out(db, user_id: int) -> bool:
    async with db.execute("SELECT COALESCE(ship_opt_out, FALSE) FROM users WHERE user_tg_id = ?", (int(user_id),)) as cur:
        row = await cur.fetchone()
    return bool(row and row[0])


async def _pause_left(db, chat_id: int, user_tg_id: int, seconds: int) -> int:
    """Сколько секунд ещё ждать (0 — пауза кончилась или её не было)."""
    async with db.execute(
        "SELECT EXTRACT(EPOCH FROM (last_at + make_interval(secs => ?) - NOW())) FROM ship_cooldowns "
        "WHERE chat_id = ? AND user_tg_id = ?",
        (int(seconds), int(chat_id), int(user_tg_id))) as cur:
        row = await cur.fetchone()
    return max(0, int(row[0])) if row and row[0] is not None else 0


async def pause_left(db, chat_id: int, user_id: int) -> int:
    """Самая долгая из двух пауз: игрока и чата."""
    from core import ship
    user_left = await _pause_left(db, chat_id, user_id, ship.COOLDOWN_USER_SECONDS)
    chat_left = await _pause_left(db, chat_id, 0, ship.COOLDOWN_CHAT_SECONDS)
    return max(user_left, chat_left)


async def remember(db, chat_id: int, user_id: int) -> None:
    """Отметить время шиппинга: строка игрока и строка чата (user_tg_id = 0)."""
    for uid in (int(user_id), 0):
        await db.execute(
            "INSERT INTO ship_cooldowns (chat_id, user_tg_id, last_at) VALUES (?, ?, NOW()) "
            "ON CONFLICT (chat_id, user_tg_id) DO UPDATE SET last_at = NOW()",
            (int(chat_id), uid))


def _ordered(user_a: int, user_b: int) -> tuple[int, int]:
    return (int(user_a), int(user_b)) if int(user_a) < int(user_b) else (int(user_b), int(user_a))


async def recent_pairs(db, chat_id: int, minutes: int) -> set[tuple[int, int]]:
    """Пары, которые уже звучали в чате за последние minutes минут: {(меньший id, больший id)}."""
    async with db.execute(
        "SELECT user_a, user_b FROM ship_recent_pairs "
        "WHERE chat_id = ? AND created_at >= NOW() - make_interval(mins => ?)",
        (int(chat_id), int(minutes))) as cur:
        return {_ordered(a, b) for a, b in await cur.fetchall()}


async def record_pair(db, chat_id: int, user_a: int, user_b: int) -> None:
    """Запомнить сыгравшую пару; заодно убрать пары старше суток."""
    low, high = _ordered(user_a, user_b)
    await db.execute(
        "INSERT INTO ship_recent_pairs (chat_id, user_a, user_b) VALUES (?, ?, ?) "
        "ON CONFLICT (chat_id, user_a, user_b) DO NOTHING",
        (int(chat_id), low, high))
    await db.execute(
        "DELETE FROM ship_recent_pairs WHERE chat_id = ? AND created_at < NOW() - make_interval(hours => 24)",
        (int(chat_id),))


async def active_pool(db, chat_id: int, days: int) -> list[tuple[int, str | None]]:
    """Кто мог бы оказаться в паре: писал в чат за последние days дней, не бот и не отказавшийся.

    Ботов отсеивает колонка user_chat_stats.is_bot (её ставит services.chat_bots); служебные
    аккаунты Telegram дополнительно отфильтровывает бот-слой — база знает их не всегда."""
    async with db.execute(
        "SELECT s.user_tg_id, u.user_tg_username FROM user_chat_stats s "
        "LEFT JOIN users u ON u.user_tg_id = s.user_tg_id "
        "WHERE s.chat_tg_id = ? AND COALESCE(s.is_left, FALSE) = FALSE "
        "AND NOT COALESCE(s.is_bot, FALSE) AND COALESCE(u.ship_opt_out, FALSE) = FALSE "
        "AND s.last_message_at >= NOW() - make_interval(days => ?) "
        "ORDER BY s.last_message_at DESC",
        (int(chat_id), int(days))) as cur:
        return [(int(r[0]), r[1]) for r in await cur.fetchall()]
