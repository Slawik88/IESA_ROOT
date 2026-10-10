"""Storage for Presence V1: when a player was last active in the Mini App and who may see it."""
from __future__ import annotations

from core.presence_v1 import DEFAULT_LEVEL, LEVELS, normalize


async def ensure_tables(db) -> None:
    async with db.execute("SELECT to_regclass('presence_v1') IS NOT NULL") as c:
        if (await c.fetchone())[0]:
            return
    await db.execute(f"""
        CREATE TABLE IF NOT EXISTS presence_v1 (
            user_id BIGINT PRIMARY KEY,
            last_seen_at TIMESTAMPTZ,
            visibility TEXT NOT NULL DEFAULT '{DEFAULT_LEVEL}' CHECK (visibility IN ({",".join(repr(x) for x in LEVELS)})),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def touch(db, user_id: int) -> None:
    await db.execute(
        "INSERT INTO presence_v1(user_id, last_seen_at) VALUES (?, NOW()) "
        "ON CONFLICT (user_id) DO UPDATE SET last_seen_at = NOW()", (int(user_id),))


async def get_many(db, user_ids: list[int]) -> dict[int, tuple]:
    """{user_id: (last_seen_at, visibility)}; players without a row are simply absent."""
    ids = [int(u) for u in dict.fromkeys(user_ids)]
    if not ids:
        return {}
    marks = ",".join("?" for _ in ids)
    async with db.execute(f"SELECT user_id, last_seen_at, visibility FROM presence_v1 WHERE user_id IN ({marks})", tuple(ids)) as c:
        return {int(r[0]): (r[1], normalize(r[2])) for r in await c.fetchall()}


async def set_visibility(db, user_id: int, level: str) -> None:
    await db.execute(
        "INSERT INTO presence_v1(user_id, visibility) VALUES (?, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET visibility = EXCLUDED.visibility, updated_at = NOW()", (int(user_id), normalize(level)))


async def last_chat_message(db, user_id: int):
    """Latest message of the player in any chat; chat activity counts as being around too."""
    async with db.execute("SELECT MAX(last_message_at) FROM user_chat_stats WHERE user_tg_id = ?", (int(user_id),)) as c:
        row = await c.fetchone()
    return row[0] if row else None
