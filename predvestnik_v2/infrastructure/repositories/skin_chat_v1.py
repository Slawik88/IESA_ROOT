"""Skins in group chats: the «Косметика в чате» switch and the news queue (purchase, raise to SSS).

News are written in the same transaction as the purchase or upgrade, so a rolled-back purchase leaves none and a replay
adds none (one row per player, skin and kind). Delivery claims (news, chat) before sending: a crash between the claim
and the send loses one message rather than sending it twice.
"""
from __future__ import annotations

MODULE_KEY = "module_cosmetics"

STATEMENTS = (
    "ALTER TABLE chat_settings ADD COLUMN IF NOT EXISTS module_cosmetics INTEGER DEFAULT 1",
    """CREATE TABLE IF NOT EXISTS skin_chat_news (
        id         BIGSERIAL PRIMARY KEY,
        user_id    BIGINT NOT NULL,
        skin_id    TEXT NOT NULL,
        kind       TEXT NOT NULL CHECK (kind IN ('buy', 'sss')),
        tier       TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        done_at    TIMESTAMPTZ,
        UNIQUE (user_id, skin_id, kind)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_skin_chat_news_pending ON skin_chat_news (user_id, created_at) WHERE done_at IS NULL",
    """CREATE TABLE IF NOT EXISTS skin_chat_news_sent (
        news_id    BIGINT NOT NULL REFERENCES skin_chat_news(id),
        chat_id    BIGINT NOT NULL,
        status     TEXT NOT NULL DEFAULT 'sending',
        error      TEXT,
        claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (news_id, chat_id)
    )""",
)


async def ensure_tables(db) -> None:
    for sql in STATEMENTS:
        await db.execute(sql)


async def cosmetics_enabled(db, chat_id: int) -> bool:
    """The chat's switch and the global one (global_module_toggles); both default to on."""
    if int(chat_id) < 0:
        async with db.execute("SELECT COALESCE(module_cosmetics, 1) FROM chat_settings WHERE chat_id = ?", (int(chat_id),)) as cur:
            row = await cur.fetchone()
        if row is not None and int(row[0]) == 0:
            return False
    async with db.execute("SELECT enabled FROM global_module_toggles WHERE module_key = ?", (MODULE_KEY,)) as cur:
        row = await cur.fetchone()
    return row is None or bool(row[0])


async def enqueue(db, user_id: int, skin_id: str, kind: str, tier: str) -> None:
    """Called inside the purchase/upgrade transaction. A repeat of the same news is ignored."""
    await db.execute(
        "INSERT INTO skin_chat_news (user_id, skin_id, kind, tier) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (user_id, skin_id, kind) DO NOTHING",
        (int(user_id), str(skin_id), str(kind), str(tier)))


async def ready_users(db, quiet_seconds: int, limit: int) -> list[int]:
    """Players whose latest pending news is at least quiet_seconds old: a run of purchases goes out as one message."""
    async with db.execute(
        "SELECT user_id FROM skin_chat_news WHERE done_at IS NULL GROUP BY user_id "
        "HAVING MAX(created_at) <= NOW() - make_interval(secs => ?) ORDER BY MIN(created_at) LIMIT ?",
        (int(quiet_seconds), int(limit))) as cur:
        return [int(r[0]) for r in await cur.fetchall()]


async def pending(db, user_id: int) -> list[dict]:
    async with db.execute(
        "SELECT id, skin_id, kind, tier, EXTRACT(EPOCH FROM NOW() - created_at)::BIGINT AS age FROM skin_chat_news "
        "WHERE user_id = ? AND done_at IS NULL ORDER BY created_at, id", (int(user_id),)) as cur:
        return [{"id": int(r[0]), "skin_id": str(r[1]), "kind": str(r[2]), "tier": str(r[3]), "age": int(r[4])}
                for r in await cur.fetchall()]


async def finish(db, news_ids: list[int]) -> None:
    if news_ids:
        await db.execute("UPDATE skin_chat_news SET done_at = NOW() WHERE id = ANY(?::bigint[]) AND done_at IS NULL", (list(news_ids),))


async def main_active_chats(db, user_id: int, days: int) -> list[int]:
    """Main chats (not linked as someone's admin chat, the bot still in) where the player wrote within `days` and did not leave."""
    async with db.execute(
        "SELECT s.chat_tg_id FROM user_chat_stats s JOIN chat_settings c ON c.chat_id = s.chat_tg_id "
        "WHERE s.user_tg_id = ? AND s.chat_tg_id < 0 AND COALESCE(s.is_left, FALSE) = FALSE "
        "AND s.last_message_at >= NOW() - make_interval(days => ?) AND c.bot_left_at IS NULL "
        "AND COALESCE(c.module_cosmetics, 1) = 1 "
        "AND NOT EXISTS (SELECT 1 FROM chat_links l WHERE l.admin_chat_id = c.chat_id) "
        "ORDER BY s.last_message_at DESC", (int(user_id), int(days))) as cur:
        return [int(r[0]) for r in await cur.fetchall()]


async def claim(db, news_ids: list[int], chat_id: int) -> list[int]:
    """Reserve these news for one chat. Returns the ids this call reserved (already reserved ones are skipped)."""
    async with db.execute(
        "INSERT INTO skin_chat_news_sent (news_id, chat_id) SELECT unnest(?::bigint[]), ? "
        "ON CONFLICT (news_id, chat_id) DO NOTHING RETURNING news_id", (list(news_ids), int(chat_id))) as cur:
        return [int(r[0]) for r in await cur.fetchall()]


async def mark(db, news_ids: list[int], chat_id: int, status: str, error: str | None) -> None:
    await db.execute(
        "UPDATE skin_chat_news_sent SET status = ?, error = ? WHERE news_id = ANY(?::bigint[]) AND chat_id = ?",
        (status, error, list(news_ids), int(chat_id)))
