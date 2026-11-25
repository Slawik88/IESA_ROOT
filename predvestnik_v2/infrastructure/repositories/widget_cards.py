"""Private presentation snapshots. No game state, wallet rules or callback tokens are recreated here."""

from __future__ import annotations

import secrets

from core import widget_cards as rules

COLUMNS = "token, bot_id, owner_id, chat_id, message_id, feature, source, parse_mode, revision, seen_revision, ready"


async def ensure_tables(db):
    await db.execute("""CREATE TABLE IF NOT EXISTS widget_card_preferences (
        user_id BIGINT PRIMARY KEY REFERENCES users(user_tg_id) ON DELETE CASCADE,
        enabled BOOLEAN NOT NULL DEFAULT TRUE
    )""")
    await db.execute("""CREATE TABLE IF NOT EXISTS widget_card_views (
        token TEXT PRIMARY KEY, bot_id BIGINT NOT NULL,
        owner_id BIGINT NOT NULL REFERENCES users(user_tg_id) ON DELETE CASCADE,
        chat_id BIGINT NOT NULL, message_id BIGINT,
        feature TEXT NOT NULL, source TEXT NOT NULL, parse_mode TEXT,
        revision BIGINT NOT NULL DEFAULT 1,
        seen_revision BIGINT NOT NULL DEFAULT 0, ready BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '7 days',
        UNIQUE(bot_id, chat_id, message_id)
    )""")
    await db.execute(
        "CREATE INDEX IF NOT EXISTS widget_card_owner_idx ON widget_card_views(owner_id, created_at DESC)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS widget_card_expiry_idx ON widget_card_views(expires_at)"
    )
    await db.execute(
        "ALTER TABLE widget_card_views ADD COLUMN IF NOT EXISTS seen_revision BIGINT NOT NULL DEFAULT 0"
    )
    await db.execute(
        "ALTER TABLE widget_card_views ADD COLUMN IF NOT EXISTS ready BOOLEAN NOT NULL DEFAULT FALSE"
    )


async def enabled(db, user_id: int) -> bool:
    async with db.execute(
        "SELECT enabled FROM widget_card_preferences WHERE user_id = ?", (user_id,)
    ) as cursor:
        row = await cursor.fetchone()
    return bool(row[0]) if row else True


async def set_enabled(db, user_id: int, value: bool):
    await db.execute(
        "INSERT INTO widget_card_preferences(user_id, enabled) VALUES (?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled",
        (user_id, value),
    )


async def create(
    db, bot_id: int, owner_id: int, feature: str, source: str, parse_mode: str | None
) -> dict:
    token = secrets.token_urlsafe(12)
    async with db.connection.transaction():
        await db.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended('widget-card:' || ?::text, 0))",
            (str(owner_id),),
        )
        async with db.execute(
            f"INSERT INTO widget_card_views(token,bot_id,owner_id,chat_id,feature,source,parse_mode,expires_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, NOW() + make_interval(days => ?)) RETURNING {COLUMNS}",
            (
                token,
                bot_id,
                owner_id,
                owner_id,
                feature,
                source,
                parse_mode,
                rules.KEEP_DAYS,
            ),
        ) as cursor:
            row = dict(await cursor.fetchone())
        await db.execute(
            "DELETE FROM widget_card_views WHERE token IN ("
            "SELECT token FROM widget_card_views WHERE owner_id = ? "
            "ORDER BY (token = ?) DESC, created_at DESC, token DESC OFFSET ?)",
            (owner_id, token, rules.MAX_USER_CARDS),
        )
    return row


async def bind(db, token: str, message_id: int):
    await db.execute(
        "UPDATE widget_card_views SET message_id = ?, ready=TRUE WHERE token = ? AND message_id IS NULL",
        (message_id, token),
    )


async def discard(db, token: str):
    await db.execute("DELETE FROM widget_card_views WHERE token = ?", (token,))


async def get(db, bot_id: int, chat_id: int, message_id: int) -> dict | None:
    async with db.execute(
        f"SELECT {COLUMNS} FROM widget_card_views WHERE bot_id=? AND chat_id=? AND message_id=? "
        "AND expires_at > NOW()",
        (bot_id, chat_id, message_id),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def replace(db, token: str, source: str, parse_mode: str | None) -> dict | None:
    async with db.execute(
        f"UPDATE widget_card_views SET source=?, parse_mode=?, revision=revision+1, ready=FALSE, seen_revision=0 "
        f"WHERE token=? AND expires_at > NOW() RETURNING {COLUMNS}",
        (source, parse_mode, token),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else None


async def acknowledge(db, token: str, revision: int):
    await db.execute(
        "UPDATE widget_card_views SET seen_revision=revision WHERE token=? AND revision=? AND expires_at>NOW()",
        (token, revision),
    )


async def finish(db, token: str, revision: int):
    await db.execute(
        "UPDATE widget_card_views SET ready=TRUE WHERE token=? AND revision=? AND expires_at>NOW()",
        (token, revision),
    )


async def cleanup(db):
    await db.execute(
        "DELETE FROM widget_card_views WHERE expires_at <= NOW() "
        "OR (message_id IS NULL AND created_at < NOW() - INTERVAL '5 minutes')"
    )
