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
    ("game_rhythm_v2",         "ᚱ Новый Ритм (dev)", False),
    ("game_minesweeper_v2",    "💣 Новый Сапёр (dev)", False),
    ("game_mafia_v1",          "🕵️ Мафия (dev)", False),
    ("game_casino_v1",         "🎰 Казино «Зал Фортуны» (жетоны)", True),
    ("game_mafia_online",      "🕵️ Межчатовая Мафия (dev)", False),
    ("content_chests_v1",       "🗝 Сундуки питомцев (canary)", False),
    ("star_dust_v1", "🌠 Звёздная пыль и VIP за активность", True),
    ("pets_v2",                "🐾 Питомцы: Тропа (dev)", False),
    ("pets_level_up_v1",      "🐾 Улучшение питомцев за валюты (dev)", False),
    ("pets_route_rewards_v1", "🐾 Награда Морой за маршруты экспедиций (dev)", False),
    ("shop_v1",               "🛒 Магазин: ключи, Шлифовка, обменник (dev)", False),
    ("gifts_v2",              "🎁 Подарки по тирам и полка в профиле (dev)", False),
    ("season_pass_v1",         "🏁 Сезонный пропуск игр (dev)", False),
    ("economy_player_exchange_v1", "📈 Биржа монет игроков (dev)", False),
    ("economy_player_exchange_shorts_v1", "📉 Шорты биржи монет игроков (dev)", False),
    ("coin_market_v2", "📈 Биржа монет v2", False),
    ("coin_market_v2_shorts", "📉 Позиции на падение v2", False),
    # Видимость игры и финансовая выдача не могут быть одним переключателем.
    ("reconstruction_real_settlement_v1", "🧾 Reconstruction: реальные награды", False),
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


async def many_enabled(db, keys) -> dict[str, bool]:
    """Пакет is_enabled одним запросом: у каждого ключа те же дефолты, что у одиночной проверки.
    Для проверок нескольких флагов в одной процедуре — один round-trip вместо нескольких."""
    wanted = list(dict.fromkeys(str(key) for key in keys))
    if not wanted:
        return {}
    async with db.execute(
        "SELECT key, enabled FROM system_flags WHERE key = ANY(?::text[])", (wanted,)
    ) as c:
        rows = {str(r["key"]): bool(r["enabled"]) for r in await c.fetchall()}
    return {key: rows.get(key, _DEFAULT_ENABLED.get(key, True)) for key in wanted}


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
