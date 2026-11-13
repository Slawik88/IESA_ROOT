"""
infrastructure/repositories/users.py — пользователи (связка с Telegram).
"""
from infrastructure.db import db, now_utc


async def upsert_user(tg_id: int, first_name: str, username: str | None) -> None:
    """Создать или обновить профиль: имя и username следуют за Telegram."""
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (tg_id, first_name, username, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (tg_id) DO UPDATE
            SET first_name = EXCLUDED.first_name, username = EXCLUDED.username
            """,
            tg_id, first_name, username, now_utc(),
        )


async def get_user(tg_id: int):
    async with db.acquire() as conn:
        return await conn.fetchrow(
            "SELECT tg_id, first_name, username, created_at, active_house_id FROM users WHERE tg_id = ?",
            tg_id,
        )


async def set_active_house(tg_id: int, house_id: int | None) -> None:
    """Выбранный дом (для состоящих в нескольких)."""
    async with db.acquire() as conn:
        await conn.execute("UPDATE users SET active_house_id = ? WHERE tg_id = ?", house_id, tg_id)
