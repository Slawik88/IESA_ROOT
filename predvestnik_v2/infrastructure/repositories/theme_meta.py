"""
infrastructure/repositories/theme_meta.py
Редактор метаданных тем (цена/редкость/описание) — theme_metadata_overrides.
DB-оверрайды перекрывают статические значения из core/themes.py THEMES без деплоя.
"""

_FIELDS = ("name", "rarity", "source", "price_mora", "price_diamonds",
           "price_zarniki", "price_dark", "obtainable_bp", "description")


async def ensure_table(db) -> None:
    """Idempotent — на случай отдельного FastAPI-процесса без init_db() бота
    (см. infrastructure/repositories/theme_templates.ensure_table)."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS theme_metadata_overrides (
            theme_id       TEXT PRIMARY KEY,
            name           TEXT,
            rarity         TEXT,
            source         TEXT,
            price_mora     INTEGER,
            price_diamonds NUMERIC,
            price_zarniki  INTEGER,
            price_dark     INTEGER,
            obtainable_bp  INTEGER DEFAULT 0,
            description    TEXT
        )
    """)
    await db.commit()


def _row_to_dict(row) -> dict:
    return dict(zip(_FIELDS, row))


async def get_override(db, theme_id: str) -> dict | None:
    async with db.execute(
        f"SELECT {', '.join(_FIELDS)} FROM theme_metadata_overrides WHERE theme_id = ?",
        (theme_id,),
    ) as c:
        row = await c.fetchone()
    return _row_to_dict(row) if row else None


async def get_all_overrides(db) -> dict[str, dict]:
    async with db.execute(
        f"SELECT theme_id, {', '.join(_FIELDS)} FROM theme_metadata_overrides"
    ) as c:
        rows = await c.fetchall()
    return {r[0]: _row_to_dict(r[1:]) for r in rows}


async def set_override(db, theme_id: str, **fields) -> None:
    values = [fields.get(f) for f in _FIELDS]
    obp_idx = _FIELDS.index("obtainable_bp")
    values[obp_idx] = 1 if values[obp_idx] else 0
    placeholders = ",".join(["?"] * (len(_FIELDS) + 1))
    set_clause = ", ".join(f"{f}=EXCLUDED.{f}" for f in _FIELDS)
    await db.execute(
        f"INSERT INTO theme_metadata_overrides (theme_id, {', '.join(_FIELDS)}) "
        f"VALUES ({placeholders}) "
        f"ON CONFLICT (theme_id) DO UPDATE SET {set_clause}",
        (theme_id, *values),
    )
    await db.commit()


async def delete_override(db, theme_id: str) -> bool:
    async with db.execute(
        "DELETE FROM theme_metadata_overrides WHERE theme_id = ? RETURNING theme_id",
        (theme_id,),
    ) as c:
        row = await c.fetchone()
    await db.commit()
    return row is not None
