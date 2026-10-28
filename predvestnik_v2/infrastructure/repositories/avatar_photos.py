"""Small copies of Telegram profile photos, kept in PostgreSQL so a deploy does not lose them.

One row per user. ``version`` names the photo (Telegram ``file_unique_id`` or a hash of the signed Mini App
photo URL); ``image`` is a 128 px WebP or NULL when the bot sees no photo. ``checked_at`` is when Telegram
was last asked. Who may see the photo is decided by services/avatar_photos.py, not here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

_ready = False


@dataclass(frozen=True)
class StoredPhoto:
    version: str | None
    has_image: bool
    checked_at: datetime


async def ensure_tables(db) -> None:
    global _ready
    if _ready:
        return
    conn = db.connection
    async with conn.transaction():   # two first requests at once must not race on CREATE TABLE
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('ensure_tables:avatar_photos', 0))")
        await conn.execute(
            """CREATE TABLE IF NOT EXISTS avatar_photos (
                user_id    BIGINT PRIMARY KEY,
                version    TEXT,
                image      BYTEA,
                checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""")
    _ready = True


async def stored(db, user_ids: list[int]) -> dict[int, StoredPhoto]:
    """What is stored for these users, without the image bytes."""
    if not user_ids:
        return {}
    await ensure_tables(db)
    rows = await db.connection.fetch(
        "SELECT user_id, version, image IS NOT NULL AS has_image, checked_at FROM avatar_photos WHERE user_id = ANY($1::bigint[])",
        [int(uid) for uid in user_ids])
    return {int(r["user_id"]): StoredPhoto(r["version"], bool(r["has_image"]), r["checked_at"]) for r in rows}


async def image(db, user_id: int) -> tuple[str, bytes] | None:
    await ensure_tables(db)
    row = await db.connection.fetchrow(
        "SELECT version, image FROM avatar_photos WHERE user_id = $1 AND image IS NOT NULL", int(user_id))
    return (row["version"], bytes(row["image"])) if row else None


async def save(db, user_id: int, version: str | None, image_bytes: bytes | None) -> None:
    await ensure_tables(db)
    await db.connection.execute(
        """INSERT INTO avatar_photos (user_id, version, image, checked_at) VALUES ($1, $2, $3, NOW())
           ON CONFLICT (user_id) DO UPDATE SET version = EXCLUDED.version, image = EXCLUDED.image, checked_at = NOW()""",
        int(user_id), version if image_bytes else None, image_bytes)


async def touch(db, user_id: int) -> None:
    """Telegram confirmed the stored photo is still current."""
    await ensure_tables(db)
    await db.connection.execute("UPDATE avatar_photos SET checked_at = NOW() WHERE user_id = $1", int(user_id))
