"""Глобальные переключатели фич (system_flags).

Ключи: tab_bp, tab_zoo, tab_market, tab_auction, tab_economy, tab_purge, tab_cosmetics, tab_quests.
Значение enabled=1 (включено) или 0 (выключено).
"""

_DEFAULTS = [
    ("tab_bp",        "🎫 Боевой пропуск"),
    ("tab_zoo",       "🐾 Зоопарк"),
    ("tab_market",    "🛒 Рынок (магазин + гача)"),
    ("tab_auction",   "🔨 Аукцион"),
    ("tab_economy",   "💰 Экономика (переводы)"),
    ("tab_purge",     "🧹 Чистки"),
    ("tab_cosmetics", "🎨 Косметика / Образы"),
    ("tab_quests",    "📋 Квесты"),
]


async def ensure_table(db) -> None:
    """Веб-процесс стартует раньше бота — без этого web падает на 'relation
    system_flags does not exist' до первого рестарта бота (init_db создаёт схему)."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS system_flags (
            key     TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            label   TEXT DEFAULT NULL
        )
    """)
    for key, label in _DEFAULTS:
        await db.execute(
            "INSERT INTO system_flags (key, enabled, label) VALUES (?, 1, ?) "
            "ON CONFLICT (key) DO NOTHING",
            (key, label),
        )
    await db.commit()


async def get_all(db) -> list[dict]:
    async with db.execute(
        "SELECT key, enabled, label FROM system_flags ORDER BY key"
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def is_enabled(db, key: str) -> bool:
    async with db.execute(
        "SELECT enabled FROM system_flags WHERE key = ?", (key,)
    ) as c:
        row = await c.fetchone()
    return bool(row["enabled"]) if row else True  # по умолчанию включено


async def set_flag(db, key: str, enabled: bool) -> bool:
    """Возвращает True если ключ нашёлся и обновлён."""
    await db.execute(
        "UPDATE system_flags SET enabled = ? WHERE key = ?",
        (int(enabled), key),
    )
    await db.commit()
    async with db.execute(
        "SELECT COUNT(*) FROM system_flags WHERE key = ?", (key,)
    ) as c:
        row = await c.fetchone()
    return bool(row[0]) if row else False
