"""
infrastructure/repositories/theme_templates.py
Theme Lab: кастомные raw-шаблоны премиум-тем профиля (profile_theme_overrides).
Правки применяются мгновенно, без деплоя.
"""


async def ensure_table(db) -> None:
    """Idempotent — создаёт profile_theme_overrides, если её ещё нет.

    bot/core/database.py:init_db() создаёт эту таблицу, но init_db()
    запускается только в процессе бота. FastAPI-процесс (где живёт Theme
    Lab) вызывает это при старте, чтобы работать без деплоя/рестарта бота.
    """
    await db.execute("""
        CREATE TABLE IF NOT EXISTS profile_theme_overrides (
            template_id TEXT PRIMARY KEY,
            raw_text    TEXT NOT NULL,
            updated_at  TIMESTAMP DEFAULT NOW(),
            updated_by  BIGINT
        )
    """)
    await db.commit()


async def get_override(db, template_id: str) -> str | None:
    async with db.execute(
        "SELECT raw_text FROM profile_theme_overrides WHERE template_id = ?",
        (template_id,),
    ) as c:
        row = await c.fetchone()
    return row[0] if row else None


async def get_all_overrides(db) -> dict[str, dict]:
    async with db.execute(
        "SELECT template_id, raw_text, updated_at, updated_by FROM profile_theme_overrides"
    ) as c:
        rows = await c.fetchall()
    return {
        r[0]: {"raw_text": r[1], "updated_at": r[2], "updated_by": r[3]}
        for r in rows
    }


async def set_override(db, template_id: str, raw_text: str, updated_by: int) -> None:
    await db.execute(
        "INSERT INTO profile_theme_overrides (template_id, raw_text, updated_at, updated_by) "
        "VALUES (?, ?, NOW(), ?) "
        "ON CONFLICT (template_id) DO UPDATE SET "
        "raw_text = EXCLUDED.raw_text, updated_at = NOW(), updated_by = EXCLUDED.updated_by",
        (template_id, raw_text, updated_by),
    )
    await db.commit()


async def delete_override(db, template_id: str) -> bool:
    async with db.execute(
        "DELETE FROM profile_theme_overrides WHERE template_id = ? RETURNING template_id",
        (template_id,),
    ) as c:
        row = await c.fetchone()
    await db.commit()
    return row is not None
