"""
infrastructure/repositories/units.py — Боёвка 3.0: юниты игрока и отряд.
user_units: владение (уровень, осколки); user_squad: 3 позиции (0 фронт/1 фланг/2 тыл).
"""


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS user_units (
            user_id     BIGINT NOT NULL,
            unit_id     TEXT NOT NULL,
            level       INTEGER NOT NULL DEFAULT 1,
            shards      INTEGER NOT NULL DEFAULT 0,
            obtained_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (user_id, unit_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS user_squad (
            user_id  BIGINT NOT NULL,
            slot     INTEGER NOT NULL,
            unit_id  TEXT NOT NULL,
            PRIMARY KEY (user_id, slot)
        )
    """)
    await db.commit()


async def get_units(db, user_id: int) -> list[dict]:
    async with db.execute(
        "SELECT unit_id, level, shards FROM user_units WHERE user_id = ? ORDER BY obtained_at",
        (user_id,),
    ) as c:
        return [dict(r) for r in await c.fetchall()]


async def get_unit(db, user_id: int, unit_id: str) -> dict | None:
    async with db.execute(
        "SELECT unit_id, level, shards FROM user_units WHERE user_id = ? AND unit_id = ?",
        (user_id, unit_id),
    ) as c:
        row = await c.fetchone()
    return dict(row) if row else None


async def grant_unit(db, user_id: int, unit_id: str) -> None:
    await db.execute(
        "INSERT INTO user_units (user_id, unit_id) VALUES (?, ?) "
        "ON CONFLICT (user_id, unit_id) DO NOTHING",
        (user_id, unit_id),
    )


async def add_shards(db, user_id: int, unit_id: str, n: int) -> None:
    """Осколки можно копить и на ещё не открытого юнита (строка level=0 недопустима —
    храним владение отдельно фактом строки; осколки без владения = строка level 1?
    Нет: строка создаётся с level 1 только при grant. Для «копилки» осколков
    не-открытого юнита используем UPSERT с level 0 → см. unlock_if_ready)."""
    await db.execute(
        "INSERT INTO user_units (user_id, unit_id, level, shards) VALUES (?, ?, 0, ?) "
        "ON CONFLICT (user_id, unit_id) DO UPDATE SET shards = user_units.shards + ?",
        (user_id, unit_id, n, n),
    )


async def spend_shards(db, user_id: int, unit_id: str, n: int) -> None:
    await db.execute(
        "UPDATE user_units SET shards = GREATEST(0, shards - ?) "
        "WHERE user_id = ? AND unit_id = ?",
        (n, user_id, unit_id),
    )


async def set_level(db, user_id: int, unit_id: str, level: int) -> None:
    await db.execute(
        "UPDATE user_units SET level = ? WHERE user_id = ? AND unit_id = ?",
        (level, user_id, unit_id),
    )


async def unlock(db, user_id: int, unit_id: str) -> None:
    """Открыть юнита, у которого копились осколки (level 0 → 1)."""
    await db.execute(
        "UPDATE user_units SET level = 1 WHERE user_id = ? AND unit_id = ? AND level = 0",
        (user_id, unit_id),
    )


async def get_squad(db, user_id: int) -> dict[int, str]:
    """{slot: unit_id} — только реально принадлежащие юниты (level >= 1)."""
    async with db.execute(
        "SELECT s.slot, s.unit_id FROM user_squad s "
        "JOIN user_units u ON u.user_id = s.user_id AND u.unit_id = s.unit_id "
        "WHERE s.user_id = ? AND u.level >= 1 ORDER BY s.slot",
        (user_id,),
    ) as c:
        return {int(r["slot"]): r["unit_id"] for r in await c.fetchall()}


async def set_squad_slot(db, user_id: int, slot: int, unit_id: str | None) -> None:
    await db.execute("DELETE FROM user_squad WHERE user_id = ? AND slot = ?", (user_id, slot))
    if unit_id:
        # один юнит — в одном слоте
        await db.execute("DELETE FROM user_squad WHERE user_id = ? AND unit_id = ?", (user_id, unit_id))
        await db.execute(
            "INSERT INTO user_squad (user_id, slot, unit_id) VALUES (?, ?, ?)",
            (user_id, slot, unit_id),
        )


async def count_units(db, user_id: int) -> int:
    """Сколько ОТКРЫТЫХ юнитов (level >= 1) у игрока."""
    async with db.execute(
        "SELECT COUNT(*) FROM user_units WHERE user_id = ? AND level >= 1", (user_id,)
    ) as c:
        row = await c.fetchone()
    return int(row[0] or 0)
