"""
infrastructure/repositories/settings.py — настройки домов, персональные
уведомления, журнал сработок планировщика.
"""
import json

from infrastructure.db import db, now_utc


# ── Настройки дома ───────────────────────────────────────────────────────────

async def house_settings_all(house_id: int) -> dict[str, str]:
    """Все переопределённые настройки дома: key → сырое значение (строка)."""
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT house_id, key, value FROM house_settings WHERE house_id = ?", house_id
        )
        return {row["key"]: row["value"] for row in rows}


async def set_house_setting(house_id: int, key: str, value) -> None:
    """Значение любого JSON-типа (bool/int/str) — реестр знает, как его читать."""
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO house_settings (house_id, key, value) VALUES (?, ?, ?)
            ON CONFLICT (house_id, key) DO UPDATE SET value = EXCLUDED.value
            """,
            house_id, key, json.dumps(value, ensure_ascii=False),
        )


# ── Персональные уведомления ─────────────────────────────────────────────────

async def notify_settings_all(house_id: int, tg_id: int) -> dict[str, str]:
    async with db.acquire() as conn:
        rows = await conn.fetch(
            "SELECT house_id, tg_id, key, value FROM user_notify_settings "
            "WHERE house_id = ? AND tg_id = ?",
            house_id, tg_id,
        )
        return {row["key"]: row["value"] for row in rows}


async def set_notify_setting(house_id: int, tg_id: int, key: str, value: str) -> None:
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_notify_settings (house_id, tg_id, key, value) VALUES (?, ?, ?, ?)
            ON CONFLICT (house_id, tg_id, key) DO UPDATE SET value = EXCLUDED.value
            """,
            house_id, tg_id, key, value,
        )


# ── Журнал планировщика ──────────────────────────────────────────────────────

async def scheduler_already_sent(house_id: int, event_key: str, day: str) -> bool:
    async with db.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT house_id FROM scheduler_log WHERE house_id = ? AND event_key = ? AND day = ?",
            house_id, event_key, day,
        )
        return row is not None


async def scheduler_mark_sent(house_id: int, event_key: str, day: str) -> None:
    """Повторная отметка не создаёт вторую строку (идемпотентность)."""
    async with db.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO scheduler_log (house_id, event_key, day, sent_at) VALUES (?, ?, ?, ?)
            ON CONFLICT (house_id, event_key, day) DO NOTHING
            """,
            house_id, event_key, day, now_utc(),
        )
