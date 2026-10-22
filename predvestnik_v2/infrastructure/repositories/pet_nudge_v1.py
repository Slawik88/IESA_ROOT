"""Storage for the gentle pet reminder. Rules: core/pet_nudge_v1.py (the upsert mirrors `visit`)."""
from __future__ import annotations

from core.pet_nudge_v1 import COOLDOWN_DAYS, MAX_SHOWS, STREAK_DAYS

_TODAY = "(NOW() AT TIME ZONE 'UTC')::date"


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS pet_nudge_v1 (
            user_id BIGINT PRIMARY KEY,
            last_day DATE NOT NULL,
            last_day_pets BOOLEAN NOT NULL DEFAULT FALSE,
            streak INTEGER NOT NULL DEFAULT 0 CHECK (streak >= 0),
            shown_on DATE NULL,
            shows INTEGER NOT NULL DEFAULT 0 CHECK (shows >= 0),
            answer TEXT NULL
        )
    """)


async def visit(db, user_id: int, pets: bool) -> None:
    """One atomic step of the day counter; parallel requests cannot double-count a day."""
    await db.execute(
        f"INSERT INTO pet_nudge_v1(user_id,last_day,last_day_pets,streak) "
        f"VALUES (?, {_TODAY}, ?, CASE WHEN ? THEN 0 ELSE 1 END) "
        "ON CONFLICT (user_id) DO UPDATE SET "
        "streak = CASE WHEN EXCLUDED.last_day_pets THEN 0 "
        "  WHEN pet_nudge_v1.last_day >= EXCLUDED.last_day THEN pet_nudge_v1.streak "
        "  WHEN pet_nudge_v1.last_day = EXCLUDED.last_day - 1 THEN pet_nudge_v1.streak + 1 "
        "  ELSE 1 END, "
        "last_day_pets = CASE WHEN pet_nudge_v1.last_day >= EXCLUDED.last_day "
        "  THEN pet_nudge_v1.last_day_pets OR EXCLUDED.last_day_pets ELSE EXCLUDED.last_day_pets END, "
        "last_day = GREATEST(pet_nudge_v1.last_day, EXCLUDED.last_day)",
        (int(user_id), bool(pets), bool(pets)),
    )


async def claim_show(db, user_id: int) -> bool:
    """Marks today's showing in the same statement that checks it is due: one card per day at most."""
    async with db.execute(
        f"UPDATE pet_nudge_v1 SET shown_on = {_TODAY}, shows = shows + 1 "
        "WHERE user_id = ? AND streak >= ? AND NOT last_day_pets AND shows < ? "
        f"AND (shown_on IS NULL OR shown_on <= {_TODAY} - ?::int) RETURNING user_id",
        (int(user_id), STREAK_DAYS, MAX_SHOWS, COOLDOWN_DAYS),
    ) as cursor:
        return await cursor.fetchone() is not None


async def answer(db, user_id: int, choice: str) -> None:
    await db.execute("UPDATE pet_nudge_v1 SET answer = ? WHERE user_id = ? AND shown_on IS NOT NULL",
                     (choice, int(user_id)))


async def oldest_pet(db, user_id: int) -> dict | None:
    async with db.execute(
        "SELECT name, species_id FROM pets WHERE owner_id = ? ORDER BY created_at, id LIMIT 1", (int(user_id),)
    ) as cursor:
        row = await cursor.fetchone()
    return {"name": row[0], "species_id": row[1]} if row else None
