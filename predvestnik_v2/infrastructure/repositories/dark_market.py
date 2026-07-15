"""
infrastructure/repositories/dark_market.py — Чёрный Рынок (R8).
Еженедельная ротация товаров за 🌑 Тёмную Мору: dark_market_current (слоты недели)
+ dark_market_purchases (1 покупка слота на игрока за неделю).
Таблицы создаются и здесь (веб), и в bot/core/database.py (бот) — гонка деплоя.
"""
from infrastructure.pg_adapter import PGAdapter


async def ensure_tables(db: PGAdapter) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS dark_market_current (
            slot         INTEGER PRIMARY KEY,
            item_id      TEXT NOT NULL,
            quantity     INTEGER NOT NULL,
            price_dark   FLOAT8 NOT NULL,
            week_key     TEXT NOT NULL
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS dark_market_purchases (
            user_id   BIGINT,
            slot      INTEGER,
            week_key  TEXT,
            PRIMARY KEY (user_id, slot, week_key)
        )
    """)
    await db.commit()


async def get_current(db: PGAdapter) -> list[dict]:
    async with db.execute(
        "SELECT slot, item_id, quantity, price_dark, week_key "
        "FROM dark_market_current ORDER BY slot ASC"
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_week_key(db: PGAdapter) -> str | None:
    async with db.execute(
        "SELECT week_key FROM dark_market_current WHERE slot = 1"
    ) as c:
        row = await c.fetchone()
    return row[0] if row else None


async def save_slots(db: PGAdapter, slots: list[dict], week_key: str) -> None:
    await db.execute("DELETE FROM dark_market_current")
    for s in slots:
        await db.execute(
            "INSERT INTO dark_market_current (slot, item_id, quantity, price_dark, week_key) "
            "VALUES (?, ?, ?, ?, ?)",
            (s["slot"], s["item_id"], s["quantity"], s["price_dark"], week_key),
        )
    await db.commit()


async def already_purchased(db: PGAdapter, user_id: int, slot: int, week_key: str) -> bool:
    async with db.execute(
        "SELECT 1 FROM dark_market_purchases WHERE user_id = ? AND slot = ? AND week_key = ?",
        (user_id, slot, week_key),
    ) as c:
        return await c.fetchone() is not None


async def record_purchase(db: PGAdapter, user_id: int, slot: int, week_key: str) -> None:
    """No commit — вызывается внутри транзакции покупки."""
    await db.execute(
        "INSERT INTO dark_market_purchases (user_id, slot, week_key) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, slot, week_key) DO NOTHING",
        (user_id, slot, week_key),
    )
