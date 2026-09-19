"""One-shot, server-bound approvals for local rank changes."""
from __future__ import annotations

import secrets


async def ensure_table(db) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS local_rank_change_requests (
            token TEXT PRIMARY KEY,
            chat_id BIGINT NOT NULL,
            initiator_id BIGINT NOT NULL,
            target_id BIGINT NOT NULL,
            target_rank_before INTEGER NOT NULL,
            new_rank_id INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ NULL,
            approved_by BIGINT NULL
        )
    """)


async def create(db, *, chat_id: int, initiator_id: int, target_id: int,
                 target_rank_before: int, new_rank_id: int) -> str:
    await ensure_table(db)
    for _ in range(3):
        token = secrets.token_urlsafe(12)
        async with db.execute(
            "INSERT INTO local_rank_change_requests "
            "(token,chat_id,initiator_id,target_id,target_rank_before,new_rank_id,expires_at) "
            "VALUES (?,?,?,?,?,?,NOW()+INTERVAL '10 minutes') ON CONFLICT DO NOTHING RETURNING token",
            (token, int(chat_id), int(initiator_id), int(target_id), int(target_rank_before), int(new_rank_id)),
        ) as cursor:
            if await cursor.fetchone():
                return token
    raise RuntimeError("could not allocate rank approval token")


async def get_open(db, *, token: str, chat_id: int) -> dict | None:
    async with db.execute(
        "SELECT * FROM local_rank_change_requests WHERE token=? AND chat_id=? "
        "AND consumed_at IS NULL AND expires_at>NOW()",
        (str(token), int(chat_id)),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def consume(db, *, token: str, chat_id: int, approved_by: int) -> dict | None:
    """Consume once under a row lock. Expired/replayed/wrong-chat tokens fail closed."""
    async with db.connection.transaction():
        async with db.execute(
            "UPDATE local_rank_change_requests SET consumed_at=NOW(),approved_by=? "
            "WHERE token=? AND chat_id=? AND consumed_at IS NULL AND expires_at>NOW() RETURNING *",
            (int(approved_by), str(token), int(chat_id)),
        ) as cursor:
            row = await cursor.fetchone()
    return dict(row) if row else None
