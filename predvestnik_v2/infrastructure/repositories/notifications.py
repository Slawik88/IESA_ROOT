"""
infrastructure/repositories/notifications.py
Настройки персональных уведомлений (Implementation Block 15).
Нет строки = включено по умолчанию.
"""


async def is_enabled(db, user_id: int, category: str) -> bool:
    """True, если уведомление этой категории включено (по умолчанию — да)."""
    async with db.execute(
        "SELECT enabled FROM user_notification_prefs WHERE user_id = ? AND category = ?",
        (user_id, category),
    ) as c:
        row = await c.fetchone()
    return True if row is None else bool(row[0])


async def get_prefs(db, user_id: int) -> dict[str, bool]:
    """Все явно заданные настройки игрока {category: enabled}."""
    async with db.execute(
        "SELECT category, enabled FROM user_notification_prefs WHERE user_id = ?",
        (user_id,),
    ) as c:
        return {r[0]: bool(r[1]) for r in await c.fetchall()}


async def set_pref(db, user_id: int, category: str, enabled: bool) -> None:
    await db.execute(
        "INSERT INTO user_notification_prefs (user_id, category, enabled) VALUES (?, ?, ?) "
        "ON CONFLICT (user_id, category) DO UPDATE SET enabled = EXCLUDED.enabled",
        (user_id, category, enabled),
    )
    await db.commit()


async def toggle(db, user_id: int, category: str) -> bool:
    """Переключить категорию. Возвращает новое состояние (enabled)."""
    new_state = not await is_enabled(db, user_id, category)
    await set_pref(db, user_id, category, new_state)
    return new_state
