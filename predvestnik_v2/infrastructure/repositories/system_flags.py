"""Глобальные переключатели фич (system_flags).

Ключи вкладок включены по умолчанию. Экспериментальные игровые поколения
добавляются выключенными и включаются только на dev/для контролируемого rollout.
Значение enabled=1 (включено) или 0 (выключено).
"""

_DEFAULTS = [
    ("tab_bp",                 "🎫 Боевой пропуск", True),
    ("tab_zoo",                "🐾 Зоопарк", True),
    ("tab_market",             "🛒 Рынок (магазин + гача)", True),
    ("tab_auction",            "🔨 Аукцион", True),
    ("tab_economy",            "💰 Экономика (переводы)", True),
    ("tab_purge",              "🧹 Чистки", True),
    ("tab_cosmetics",          "🎨 Косметика / Образы", True),
    ("tab_quests",             "📋 Квесты", True),
    ("game_reconstruction_v1", "🧭 Reconstruction 3.0 (dev)", False),
]

_DEFAULT_ENABLED = {key: enabled for key, _label, enabled in _DEFAULTS}


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
    for key, label, enabled in _DEFAULTS:
        await db.execute(
            "INSERT INTO system_flags (key, enabled, label) VALUES (?, ?, ?) "
            "ON CONFLICT (key) DO NOTHING",
            (key, int(enabled), label),
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
    # Неизвестные исторические ключи сохраняют прежнее fail-open поведение.
    # Известный экспериментальный ключ остаётся fail-closed даже до ensure_table.
    return bool(row["enabled"]) if row else _DEFAULT_ENABLED.get(key, True)


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
