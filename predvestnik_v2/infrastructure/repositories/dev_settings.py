"""Числовые настройки, крутимые дев-консолью без деплоя (Growth-полиш 2026-07-13).
Аналог system_flags.py, но для чисел, а не вкл/выкл — например порог тишины чата
для реактивации (services/scheduler.py::chest_spawn_task)."""

_DEFAULTS = [
    ("quiet_chat_reactivation_days", 3.0, "🌙 Дней полной тишины в чате до реактивации"),
]


async def ensure_table(db) -> None:
    """Веб-процесс стартует раньше бота — та же гонка, что у system_flags."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS dev_numeric_settings (
            key     TEXT PRIMARY KEY,
            value   FLOAT8 NOT NULL,
            label   TEXT DEFAULT NULL
        )
    """)
    for key, value, label in _DEFAULTS:
        await db.execute(
            "INSERT INTO dev_numeric_settings (key, value, label) VALUES (?, ?, ?) "
            "ON CONFLICT (key) DO NOTHING",
            (key, value, label),
        )
    await db.commit()


async def get_all(db) -> list[dict]:
    async with db.execute(
        "SELECT key, value, label FROM dev_numeric_settings ORDER BY key"
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_value(db, key: str, default: float) -> float:
    async with db.execute(
        "SELECT value FROM dev_numeric_settings WHERE key = ?", (key,)
    ) as c:
        row = await c.fetchone()
    return float(row["value"]) if row else default


async def set_value(db, key: str, value: float) -> bool:
    """Возвращает True если ключ нашёлся и обновлён."""
    await db.execute(
        "UPDATE dev_numeric_settings SET value = ? WHERE key = ?",
        (value, key),
    )
    await db.commit()
    async with db.execute(
        "SELECT COUNT(*) FROM dev_numeric_settings WHERE key = ?", (key,)
    ) as c:
        row = await c.fetchone()
    return bool(row[0]) if row else False
