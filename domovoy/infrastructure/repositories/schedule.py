"""
infrastructure/repositories/schedule.py — версии графика и дни уборки.
"""
from infrastructure.db import db, now_utc


# ── Версии графика ───────────────────────────────────────────────────────────

async def get_latest_version(house_id: int):
    async with db.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, house_id, weekday_map, active_from, created_at
            FROM schedule_versions WHERE house_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            house_id,
        )


async def replace_open_days(
    house_id: int, weekday_map_json: str, active_from: str,
    planned: list[tuple[int, str]],
) -> int:
    """Смена графика одной транзакцией: новая версия + переложить будущие планы.

    Прошлые дни и уже закрытые не трогаются. Возвращает id новой версии.
    """
    async with db.transaction() as conn:
        version_id = await conn.insert(
            """
            INSERT INTO schedule_versions (house_id, weekday_map, active_from, created_at)
            VALUES (?, ?, ?, ?)
            """,
            house_id, weekday_map_json, active_from, now_utc(),
        )
        await conn.execute(
            """
            DELETE FROM cleaning_days
            WHERE house_id = ? AND status = 'open' AND planned_date >= ?
            """,
            house_id, active_from,
        )
        for tg_id, planned_date in planned:
            await conn.execute(
                """
                INSERT INTO cleaning_days (house_id, tg_id, planned_date, status)
                VALUES (?, ?, ?, 'open')
                ON CONFLICT (house_id, planned_date, tg_id) DO NOTHING
                """,
                house_id, tg_id, planned_date,
            )
    return version_id


# ── Дни уборки ───────────────────────────────────────────────────────────────

async def get_day(day_id: int):
    async with db.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, house_id, tg_id, planned_date, status, actual_date, closed_by, closed_at
            FROM cleaning_days WHERE id = ?
            """,
            day_id,
        )


# ── Дни уборки ───────────────────────────────────────────────────────────────

async def add_day(house_id: int, tg_id: int, planned_date: str) -> bool:
    """Положить плановый день; существующий не трогаем (идемпотентно)."""
    async with db.acquire() as conn:
        rowcount = await conn.execute(
            """
            INSERT INTO cleaning_days (house_id, tg_id, planned_date, status)
            VALUES (?, ?, ?, 'open')
            ON CONFLICT (house_id, planned_date, tg_id) DO NOTHING
            """,
            house_id, tg_id, planned_date,
        )
        return rowcount > 0


async def days_on(house_id: int, planned_date: str) -> list:
    async with db.acquire() as conn:
        return await conn.fetch(
            """
            SELECT d.id, d.house_id, d.tg_id, d.planned_date, d.status, d.actual_date,
                   d.closed_by, m.display_name
            FROM cleaning_days d
            LEFT JOIN memberships m ON m.house_id = d.house_id AND m.tg_id = d.tg_id
            WHERE d.house_id = ? AND d.planned_date = ?
            ORDER BY d.id
            """,
            house_id, planned_date,
        )


async def oldest_open_up_to(house_id: int, tg_id: int, up_to_date: str):
    """Самый старый незакрытый день жильца не позднее даты (просроченные — тоже)."""
    async with db.acquire() as conn:
        return await conn.fetchrow(
            """
            SELECT id, house_id, tg_id, planned_date, status, actual_date, closed_by
            FROM cleaning_days
            WHERE house_id = ? AND tg_id = ? AND status = 'open' AND planned_date <= ?
            ORDER BY planned_date LIMIT 1
            """,
            house_id, tg_id, up_to_date,
        )


async def open_days_between(house_id: int, from_date: str, to_date: str) -> list:
    async with db.acquire() as conn:
        return await conn.fetch(
            """
            SELECT id, house_id, tg_id, planned_date, status
            FROM cleaning_days
            WHERE house_id = ? AND status = 'open' AND planned_date BETWEEN ? AND ?
            ORDER BY planned_date
            """,
            house_id, from_date, to_date,
        )


async def close_day(day_id: int, actual_date: str, closed_by: int) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE cleaning_days
            SET status = 'done', actual_date = ?, closed_by = ?, closed_at = ?
            WHERE id = ? AND status = 'open'
            """,
            actual_date, closed_by, now_utc(), day_id,
        )


async def cancel_day(day_id: int, closed_by: int) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            UPDATE cleaning_days
            SET status = 'canceled', closed_by = ?, closed_at = ?
            WHERE id = ? AND status = 'open'
            """,
            closed_by, now_utc(), day_id,
        )


async def month_history(house_id: int, month: str) -> list:
    """Все дни месяца для календаря и статистики."""
    async with db.acquire() as conn:
        return await conn.fetch(
            """
            SELECT d.id, d.tg_id, d.planned_date, d.status, d.actual_date, d.closed_by,
                   m.display_name
            FROM cleaning_days d
            LEFT JOIN memberships m ON m.house_id = d.house_id AND m.tg_id = d.tg_id
            WHERE d.house_id = ? AND d.planned_date LIKE ?
            ORDER BY d.planned_date, d.id
            """,
            house_id, month + "%",
        )
