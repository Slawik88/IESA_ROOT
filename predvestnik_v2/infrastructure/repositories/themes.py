"""
infrastructure/repositories/themes.py
Владение темами профиля и активная тема.
"""
from core.themes import DEFAULT_THEME


async def owns_theme(db, user_id: int, theme_id: str) -> bool:
    if theme_id == DEFAULT_THEME:
        return True
    async with db.execute(
        "SELECT 1 FROM user_themes WHERE user_id = ? AND theme_id = ?",
        (user_id, theme_id),
    ) as c:
        return (await c.fetchone()) is not None


async def grant_theme(db, user_id: int, theme_id: str) -> bool:
    """Add a theme to the user's collection. Returns True if newly added."""
    try:
        await db.execute(
            "INSERT INTO user_themes (user_id, theme_id) VALUES (?, ?) "
            "ON CONFLICT (user_id, theme_id) DO NOTHING",
            (user_id, theme_id),
        )
        return True
    except Exception:
        return False


async def list_owned(db, user_id: int) -> set[str]:
    async with db.execute(
        "SELECT theme_id FROM user_themes WHERE user_id = ?", (user_id,)
    ) as c:
        owned = {r[0] for r in await c.fetchall()}
    owned.add(DEFAULT_THEME)
    return owned


async def get_active_theme(db, user_id: int) -> str:
    async with db.execute(
        "SELECT active_theme FROM users WHERE user_tg_id = ?", (user_id,)
    ) as c:
        row = await c.fetchone()
    return (row[0] if row and row[0] else DEFAULT_THEME)


async def set_active_theme(db, user_id: int, theme_id: str) -> None:
    await db.execute(
        "INSERT INTO users (user_tg_id, active_theme) VALUES (?, ?) "
        "ON CONFLICT (user_tg_id) DO UPDATE SET active_theme = EXCLUDED.active_theme",
        (user_id, theme_id),
    )
    await db.commit()
