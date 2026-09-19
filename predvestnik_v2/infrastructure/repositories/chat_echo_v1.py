"""Transactional storage for the chat-native Echo event."""
from __future__ import annotations

from typing import Any


async def ensure_tables(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chat_echo_events (
            id BIGSERIAL PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            policy_version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'creating',
            target INTEGER NOT NULL,
            quorum INTEGER NOT NULL,
            active_members_7d INTEGER NOT NULL,
            started_by BIGINT NOT NULL,
            message_id BIGINT NULL,
            finale_id TEXT NULL,
            starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ends_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ NULL,
            CONSTRAINT chat_echo_status_ck CHECK (status IN ('creating','active','completed','expired','cancelled','failed')),
            CHECK (target >= quorum AND quorum >= 3)
        )
    """)
    await db.execute("ALTER TABLE chat_echo_events DROP CONSTRAINT IF EXISTS chat_echo_status_ck")
    await db.execute("ALTER TABLE chat_echo_events DROP CONSTRAINT IF EXISTS chat_echo_events_status_check")
    await db.execute(
        "ALTER TABLE chat_echo_events ADD CONSTRAINT chat_echo_status_ck "
        "CHECK (status IN ('creating','active','completed','expired','cancelled','failed'))"
    )
    await db.execute("ALTER TABLE chat_echo_events ALTER COLUMN status SET DEFAULT 'creating'")
    await db.execute("DROP INDEX IF EXISTS uq_chat_echo_one_active")
    await db.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_echo_one_active
        ON chat_echo_events(chat_id) WHERE status IN ('creating','active')
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chat_echo_contributions (
            event_id BIGINT NOT NULL REFERENCES chat_echo_events(id),
            user_id BIGINT NOT NULL,
            symbol_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (event_id, user_id),
            CHECK (symbol_id IN ('bell','tide','silence'))
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS chat_echo_eligible (
            event_id BIGINT NOT NULL REFERENCES chat_echo_events(id),
            user_id BIGINT NOT NULL,
            PRIMARY KEY (event_id, user_id)
        )
    """)
    await db.commit()


async def lock_chat(db, chat_id: int) -> None:
    await db.execute("INSERT INTO chat_settings (chat_id) VALUES (?) ON CONFLICT DO NOTHING", (int(chat_id),))
    async with db.execute("SELECT chat_id FROM chat_settings WHERE chat_id = ? FOR UPDATE", (int(chat_id),)) as cursor:
        await cursor.fetchone()


async def opt_in_enabled(db, chat_id: int) -> bool:
    async with db.execute("SELECT COALESCE(echo_events_enabled, 0) FROM chat_settings WHERE chat_id = ?", (int(chat_id),)) as cursor:
        row = await cursor.fetchone()
    return bool(row and row[0])


async def expire_overdue(db, chat_id: int) -> None:
    await db.execute(
        "UPDATE chat_echo_events SET status = 'expired' WHERE chat_id = ? "
        "AND status = 'active' AND ends_at <= NOW()",
        (int(chat_id),),
    )


async def recover_stale_creating(db, chat_id: int) -> None:
    await db.execute(
        "UPDATE chat_echo_events SET status='failed' WHERE chat_id=? "
        "AND status='creating' AND starts_at <= NOW() - INTERVAL '2 minutes'",
        (int(chat_id),),
    )


async def active_event(db, chat_id: int) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM chat_echo_events WHERE chat_id = ? AND status = 'active' "
        "ORDER BY id DESC LIMIT 1",
        (int(chat_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def open_event(db, chat_id: int) -> dict[str, Any] | None:
    async with db.execute(
        "SELECT * FROM chat_echo_events WHERE chat_id=? AND status IN ('creating','active') "
        "ORDER BY id DESC LIMIT 1",
        (int(chat_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def latest_started_at(db, chat_id: int):
    async with db.execute(
        "SELECT MAX(starts_at) FROM chat_echo_events WHERE chat_id = ? "
        "AND status IN ('active','completed','expired')",
        (int(chat_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return row[0] if row else None


async def active_member_count(db, chat_id: int) -> int:
    async with db.execute(
        "SELECT COUNT(*) FROM user_chat_stats WHERE chat_tg_id = ? AND is_left = FALSE "
        "AND last_message_at >= NOW() - INTERVAL '7 days'",
        (int(chat_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def eligible_candidates(db, chat_id: int, limit: int = 100) -> list[dict]:
    async with db.execute(
        "SELECT s.user_tg_id AS user_id, s.membership_since, "
        "s.user_messages_count_all_time, s.local_rank FROM user_chat_stats s "
        "LEFT JOIN chat_blacklist cb ON cb.chat_id=s.chat_tg_id AND cb.user_id=s.user_tg_id "
        "LEFT JOIN global_blacklist gb ON gb.entity_type='user' AND gb.entity_id=s.user_tg_id "
        "WHERE s.chat_tg_id=? AND s.is_left=FALSE AND COALESCE(s.is_bot,FALSE)=FALSE "
        "AND s.last_message_at >= NOW() - INTERVAL '7 days' "
        "AND cb.user_id IS NULL AND gb.entity_id IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM global_sanctions gs "
        "WHERE gs.target_type='user' AND gs.target_id=s.user_tg_id "
        "AND gs.sanction_type IN ('restrict','ban') AND gs.revoked_at IS NULL "
        "AND (gs.expires_at IS NULL OR gs.expires_at > NOW())) "
        "ORDER BY s.user_messages_count_all_time DESC LIMIT ?",
        (int(chat_id), int(limit)),
    ) as cursor:
        return [dict(row) for row in await cursor.fetchall()]


async def create_event(db, *, chat_id: int, policy_version: str, target: int, quorum: int,
                       active_members_7d: int, started_by: int, duration_hours: int,
                       eligible_user_ids: list[int]) -> dict:
    async with db.execute(
        "INSERT INTO chat_echo_events "
        "(chat_id,policy_version,target,quorum,active_members_7d,started_by,ends_at) "
        "VALUES (?,?,?,?,?,?,NOW() + (? * INTERVAL '1 hour')) RETURNING *",
        (int(chat_id), policy_version, int(target), int(quorum), int(active_members_7d), int(started_by), int(duration_hours)),
    ) as cursor:
        event = dict(await cursor.fetchone())
    for user_id in eligible_user_ids:
        await db.execute(
            "INSERT INTO chat_echo_eligible (event_id,user_id) VALUES (?,?)",
            (int(event["id"]), int(user_id)),
        )
    return event


async def bind_message(db, event_id: int, chat_id: int, message_id: int, duration_hours: int) -> dict | None:
    async with db.execute(
        "UPDATE chat_echo_events SET message_id=?, status='active', starts_at=NOW(), "
        "ends_at=NOW() + (? * INTERVAL '1 hour') WHERE id=? AND chat_id=? "
        "AND status='creating' RETURNING *",
        (int(message_id), int(duration_hours), int(event_id), int(chat_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def cancel_unpublished(db, event_id: int, chat_id: int) -> None:
    await db.execute(
        "UPDATE chat_echo_events SET status = 'failed' WHERE id = ? AND chat_id = ? "
        "AND status = 'creating' AND message_id IS NULL",
        (int(event_id), int(chat_id)),
    )


async def lock_event(db, event_id: int, chat_id: int) -> dict | None:
    async with db.execute(
        "SELECT * FROM chat_echo_events WHERE id = ? AND chat_id = ? FOR UPDATE",
        (int(event_id), int(chat_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def eligibility(db, user_id: int, chat_id: int) -> dict | None:
    async with db.execute(
        "SELECT joined_at, user_messages_count_all_time, local_rank, is_left "
        "FROM user_chat_stats WHERE user_tg_id = ? AND chat_tg_id = ?",
        (int(user_id), int(chat_id)),
    ) as cursor:
        row = await cursor.fetchone()
        return dict(row) if row else None


async def in_snapshot(db, event_id: int, user_id: int) -> bool:
    async with db.execute(
        "SELECT 1 FROM chat_echo_eligible WHERE event_id=? AND user_id=?",
        (int(event_id), int(user_id)),
    ) as cursor:
        return (await cursor.fetchone()) is not None


async def set_enabled(db, chat_id: int, enabled: bool) -> dict | None:
    await db.execute(
        "UPDATE chat_settings SET echo_events_enabled=? WHERE chat_id=?",
        (int(bool(enabled)), int(chat_id)),
    )
    if enabled:
        return None
    async with db.execute(
        "UPDATE chat_echo_events SET status='cancelled' WHERE chat_id=? "
        "AND status IN ('creating','active') RETURNING *",
        (int(chat_id),),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def existing_contribution(db, event_id: int, user_id: int) -> str | None:
    async with db.execute(
        "SELECT symbol_id FROM chat_echo_contributions WHERE event_id = ? AND user_id = ?",
        (int(event_id), int(user_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return str(row[0]) if row else None


async def insert_contribution(db, event_id: int, user_id: int, symbol_id: str) -> bool:
    async with db.execute(
        "INSERT INTO chat_echo_contributions (event_id,user_id,symbol_id) VALUES (?,?,?) "
        "ON CONFLICT DO NOTHING RETURNING user_id",
        (int(event_id), int(user_id), symbol_id),
    ) as cursor:
        return (await cursor.fetchone()) is not None


async def counts(db, event_id: int) -> dict[str, int]:
    async with db.execute(
        "SELECT symbol_id, COUNT(*) FROM chat_echo_contributions WHERE event_id = ? GROUP BY symbol_id",
        (int(event_id),),
    ) as cursor:
        rows = await cursor.fetchall()
    return {str(row[0]): int(row[1]) for row in rows}


async def complete(db, event_id: int, finale_id: str) -> dict | None:
    async with db.execute(
        "UPDATE chat_echo_events SET status='completed', finale_id=?, completed_at=NOW() "
        "WHERE id=? AND status='active' RETURNING *",
        (finale_id, int(event_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None
