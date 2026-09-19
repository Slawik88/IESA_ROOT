"""Durable ownership and saved selection for whole-app skins."""
from __future__ import annotations


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS global_skin_v1_owned (
            user_id BIGINT NOT NULL,
            skin_id TEXT NOT NULL,
            source TEXT NOT NULL,
            granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(user_id, skin_id)
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS global_skin_v1_selection (
            user_id BIGINT PRIMARY KEY,
            skin_id TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def owned_ids(db, user_id: int) -> set[str]:
    async with db.execute(
        "SELECT skin_id FROM global_skin_v1_owned WHERE user_id=? ORDER BY granted_at,skin_id",
        (int(user_id),),
    ) as cursor:
        return {str(row[0]) for row in await cursor.fetchall()}


async def saved_selection(db, user_id: int) -> str | None:
    async with db.execute(
        "SELECT skin_id FROM global_skin_v1_selection WHERE user_id=?",
        (int(user_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return str(row[0]) if row else None


async def set_selection(db, user_id: int, skin_id: str) -> None:
    await db.execute(
        "INSERT INTO global_skin_v1_selection(user_id,skin_id) VALUES (?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET skin_id=EXCLUDED.skin_id,updated_at=NOW()",
        (int(user_id), str(skin_id)),
    )


async def grant(db, user_id: int, skin_id: str, *, source: str) -> None:
    await db.execute(
        "INSERT INTO global_skin_v1_owned(user_id,skin_id,source) VALUES (?,?,?) "
        "ON CONFLICT(user_id,skin_id) DO NOTHING",
        (int(user_id), str(skin_id), str(source)),
    )
    async with db.execute(
        "SELECT source FROM global_skin_v1_owned WHERE user_id=? AND skin_id=?",
        (int(user_id), str(skin_id)),
    ) as cursor:
        row = await cursor.fetchone()
    if not row or str(row[0]) != str(source):
        raise ValueError("global skin grant source conflicts with existing ownership")
